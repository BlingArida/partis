import os
import glob
import sys
import numpy
import random
from collections import OrderedDict
import time
import csv
from subprocess import check_call, Popen, check_output, PIPE
import itertools
sys.path.insert(1, './python')
csv.field_size_limit(sys.maxsize)
from hist import Hist
import seqfileopener
import utils
import baseutils
# from clusterplot import ClusterPlot
from clusterpath import ClusterPath
import plotting

changeorandomcrapstr = '_db-pass_parse-select_clone-pass.tab'
metrics = ['adj_mi', 'ccf_under', 'ccf_over']

# ----------------------------------------------------------------------------------------
def get_title(args, label, n_leaves, mut_mult):
    if args.data:
        title = 'data (%s %s)' % (args.dataset, label)
    else:
        title = '%d leaves, %dx mutation' % (n_leaves, mut_mult)
        if args.indels:
            title += ', indels'
    return title

# ----------------------------------------------------------------------------------------
def leafmutstr(args, n_leaves, mut_mult):
    return_str = 'simu-' + str(n_leaves) + '-leaves-' + str(mut_mult) + '-mutate'
    if args.indels:
        return_str += '-indels'
    if args.lonely_leaves:
        return_str += '-lonely-leaves'
    return return_str

# ----------------------------------------------------------------------------------------
def get_outdirname(args, label, no_subset=False):
    outdirname = args.fsdir + '/' + label
    if not no_subset:
        if args.subset is not None:
            outdirname += '/subset-' + str(args.subset)
        if args.istartstop is not None:
            outdirname += '/istartstop-' + '-'.join([str(i) for i in args.istartstop])
    return outdirname

# ----------------------------------------------------------------------------------------
def get_simfname(args, label, n_leaves, mut_mult, no_subset=False):
    return get_outdirname(args, label, no_subset=no_subset) + '/' + leafmutstr(args, n_leaves, mut_mult) + '.csv'

# ----------------------------------------------------------------------------------------
def get_program_workdir(args, program_name, label, n_leaves, mut_mult):
    basedir = '/fh/fast/matsen_e/dralph/work/' + program_name + '/' + label
    if args.data:
        outdir = basedir + '/data'
    else:
        outdir = basedir + '/' + leafmutstr(args, n_leaves, mut_mult)
    if args.subset is not None:
        outdir += '/subset-' + str(args.subset)
    if args.istartstop is not None:
        outdir += '/istartstop-' + '-'.join([str(i) for i in args.istartstop])
    return outdir

# ----------------------------------------------------------------------------------------
def get_changeo_outdir(args, label, n_leaves, mut_mult):
    if args.bak:
        changeo_fsdir = '/fh/fast/matsen_e/dralph/work/changeo.bak/' + label
    else:
        changeo_fsdir = '/fh/fast/matsen_e/dralph/work/changeo/' + label
    if args.data:
        imgtdir = changeo_fsdir + '/data'
    else:
        imgtdir = changeo_fsdir + '/' + leafmutstr(args, n_leaves, mut_mult).replace('-', '_')
    return imgtdir

# ----------------------------------------------------------------------------------------
def deal_with_parse_results(info, outdir, vname, partition, hist, metrics=None, info_vname=None):
    if info_vname is None:
        info_vname = vname
    if partition is not None:
        info['partitions'][info_vname] = partition
    info['hists'][info_vname] = hist
    hist.write(outdir + '/hists/' + vname + '.csv')
    if metrics is not None and vname != 'true':
        for mname, val in metrics.items():
            info[mname][info_vname] = val
            write_float_val(outdir + '/' + mname + '/' + vname, val, mname)

# ----------------------------------------------------------------------------------------
def parse_vollmers(args, info, seqfname, outdir, reco_info, rebin=None):
    vollmers_fname = seqfname.replace('.csv', '-run-viterbi.csv')
    n_lines = 0
    with open(vollmers_fname) as vfile:
        vreader = csv.DictReader(vfile)
        for line in vreader:
            n_lines += 1
            partitionstr = line['partition'] if 'partition' in line else line['clusters']  # backwards compatibility -- used to be 'clusters' and there's still a few old files floating around
            partition = utils.get_partition_from_str(partitionstr)
            metrics = None
            if not args.data:
                true_partition = utils.get_true_partition(reco_info)
                truehist = plotting.get_cluster_size_hist(true_partition, rebin=rebin)
                deal_with_parse_results(info, outdir, 'true', true_partition, truehist, metrics=None)
                utils.check_intersection_and_complement(partition, true_partition)
                ccfs = utils.correct_cluster_fractions(partition, reco_info)
                metrics = {'adj_mi' : float(line['adj_mi']), 'ccf_under' : ccfs[0], 'ccf_over' : ccfs[1]}

            deal_with_parse_results(info, outdir, 'vollmers-' + line['threshold'], partition, plotting.get_cluster_size_hist(partition, rebin=rebin), metrics)

    if n_lines < 1:
        raise Exception('zero partition lines read from %s' % vollmers_fname)

# ----------------------------------------------------------------------------------------
def parse_changeo(args, label, n_leaves, mut_mult, info, simfbase, outdir, rebin=None):
    raise Exception('rerun all the changeo stuff accounting for missing uids')
    indir = get_changeo_outdir(args, label, n_leaves, mut_mult)  #fsdir.replace('/partis-dev/_output', '/changeo')
    if args.data:
        fbase = 'data'
    else:
        fbase = simfbase.replace('-', '_')
    if args.bak:
        infname = indir + '/' + fbase + changeorandomcrapstr
    else:
        # infname = indir + '/' + fbase + '/' + changeorandomcrapstr
        infname = indir + '/' + changeorandomcrapstr
    if args.subset is not None:
        infname = infname.replace(changeorandomcrapstr, 'subset-' + str(args.subset) + changeorandomcrapstr)
    if args.istartstop is not None:
        infname = infname.replace(changeorandomcrapstr, 'istartstop_' + '_'.join([str(i) for i in args.istartstop]) + changeorandomcrapstr)

    id_clusters = {}  # map from cluster id to list of seq ids
    with open(infname) as chfile:
        reader = csv.DictReader(chfile, delimiter='\t')
        for line in reader:
            clid = line['CLONE']
            uid = line['SEQUENCE_ID']
            if clid not in id_clusters:
                id_clusters[clid] = []
            id_clusters[clid].append(uid)

    partition = [ids for ids in id_clusters.values()]
    metrics = None
    if not args.data:
        adj_mi_fname = infname.replace(changeorandomcrapstr, '-adj_mi.csv')
        metrics = {'adj_mi' : read_float_val(adj_mi_fname, 'adj_mi')}
        for etype in ['under', 'over']:
            ccf_fname = infname.replace(changeorandomcrapstr, '-ccf_' + etype+ '.csv')
            metrics['ccf_' + etype] = read_float_val(ccf_fname, 'ccf_' + etype)
    deal_with_parse_results(info, outdir, 'changeo', partition, plotting.get_cluster_size_hist(partition, rebin=rebin), metrics)

# ----------------------------------------------------------------------------------------
def parse_mixcr(args, info, seqfname, outdir):
    raise Exception('rerun all the mixcr stuff accounting for missing uids')
    mixfname = seqfname.replace('.csv', '-mixcr.tsv')
    cluster_size_list = []  # put 'em in a list first so we know where to put the hist limits
    max_cluster_size = 1
    with open(mixfname) as mixfile:
        reader = csv.DictReader(mixfile, delimiter='\t')
        for line in reader:
            csize = int(line['Clone count'])
            cluster_size_list.append(csize)
            if csize > max_cluster_size:
                max_cluster_size = csize
    mixhist = Hist(max_cluster_size, 0.5, max_cluster_size + 0.5)
    for csize in cluster_size_list:
        mixhist.fill(csize)
    deal_with_parse_results(info, outdir, 'mixcr', None, mixhist, None)

# ----------------------------------------------------------------------------------------
def parse_partis(args, action, info, seqfname, outdir, reco_info, rebin=None):
    cpath = ClusterPath()
    cpath.readfile(seqfname.replace('.csv', '-' + action + '.csv'))
    hist = plotting.get_cluster_size_hist(cpath.partitions[cpath.i_best], rebin=rebin)
    partition = cpath.partitions[cpath.i_best]
    vname = action
    info_vname = vname + ' partis'  # arg, shouldn't have done it that way
    metrics = None
    if not args.data:
        ccfs = utils.correct_cluster_fractions(cpath.partitions[cpath.i_best], reco_info)
        metrics = {'adj_mi' : cpath.adj_mis[cpath.i_best], 'ccf_under' : ccfs[0], 'ccf_over' : ccfs[1]}
    deal_with_parse_results(info, outdir, action, partition, hist, metrics, info_vname)

# ----------------------------------------------------------------------------------------
def add_synthetic_partition_info(args, info, seqfname, outdir, reco_info, rebin=None):
    print 'TODO this is slow for large samples, don\'t rerun it unless you need to'
    for misfrac in [0.1, 0.9]:
        for mistype in ['singletons', 'reassign']:
            vname = 'misassign-%.2f-%s' % (misfrac, mistype)
            new_partition = utils.generate_incorrect_partition(info['partitions']['true'], misfrac, mistype)
            info['partitions'][vname] = new_partition
            info['adj_mi'][vname] = utils.adjusted_mutual_information(info['partitions']['true'], new_partition)
            write_float_val(outdir + '/adj_mi/' + vname + '.csv', info['adj_mi'][vname], 'adj_mi')
            ccfs = utils.correct_cluster_fractions(new_partition, reco_info)
            info['ccf_under'][vname] = ccfs[0]
            info['ccf_over'][vname] = ccfs[1]
            write_float_val(outdir + '/ccf_under/' + vname + '.csv', ccfs[0], 'ccf_under')
            write_float_val(outdir + '/ccf_over/' + vname + '.csv', ccfs[1], 'ccf_over')
            hist = plotting.get_cluster_size_hist(new_partition, rebin=rebin)
            hist.write(outdir + '/hists/' + vname + '.csv')
            info['hists'][vname] = hist

# ----------------------------------------------------------------------------------------
def write_float_val(fname, val, valname):
    if not os.path.exists(os.path.dirname(fname)):
        os.makedirs(os.path.dirname(fname))
    with open(fname, 'w') as outfile:
        writer = csv.DictWriter(outfile, [valname])
        writer.writerow({valname : val})

# ----------------------------------------------------------------------------------------
def read_float_val(fname, valname):
    """ read file with a single number """
    with open(fname) as infile:
        reader = csv.DictReader(infile, fieldnames=[valname])
        for line in reader:
            return float(line[valname])
    raise Exception('something wrong with %s file' % fname)

# ----------------------------------------------------------------------------------------
def make_a_distance_plot(args, metric, combinations, reco_info, cachevals, plotdir, plotname, plottitle):
    def get_joint_key(k1, k2):
        """ figure out which order we have <k1>, <k2> in the cache (if neither, return None) """
        jk1 = k1 + ':' + k2
        jk2 = k2 + ':' + k1
        if jk1 in cachevals:
            return jk1
        elif jk2 in cachevals:
            return jk2
        else:
            return None

    hstyles = ['plain', 'zoom-logy']
    hists = {hs : OrderedDict() for hs in hstyles}
    htypes = ['nearest-clones', 'farthest-clones', 'all-clones', 'not']
    for hs in hstyles:
        if metric == 'logprob':
            nbins, xmin, xmax = 40, -55, 70
        elif metric == 'naive_hfrac':
            if 'zoom' in hs:
                nbins, xmin, xmax = 30, 0., 0.2
            else:
                nbins, xmin, xmax = 70, 0., 0.65
        for ht in htypes:
            hists[hs][ht] = Hist(nbins, xmin, xmax)
    # hists['nearest-clones'], hists['farthest-clones'], hists['all-clones'], hists['not'] = [Hist(nbins, xmin, xmax) for _ in range(4)]
    bigvals, smallvals = {}, {}
    for key_a, key_b in combinations:  # <key_[ab]> is colon-separated string (not a list of keys)
        a_ids, b_ids = key_a.split(':'), key_b.split(':')
        if not utils.from_same_event(reco_info, a_ids) or not utils.from_same_event(reco_info, b_ids):  # skip clusters that were erroneously merged -- i.e., in effect, assume the previous step didn't screw up at all
            raise Exception('woop')
        jk = get_joint_key(key_a, key_b)
        if jk is None:  # if we don't have the joint logprob cached
            continue

        if metric == 'logprob':
            # jk = get_joint_key(key_a, key_b)
            # if jk is None:  # if we don't have the joint logprob cached
            #     continue
            lratio = cachevals[jk] - cachevals[key_a] - cachevals[key_b]
            # print '%f - %f - %f = %f' % (cachevals[jk], cachevals[key_a], cachevals[key_b], lratio),
            mval = lratio
        elif metric == 'naive_hfrac':
            # mval = utils.hamming_fraction(cachevals[key_a], cachevals[key_b])
            mval = cachevals[jk]
        else:
            assert False

        if utils.from_same_event(reco_info, a_ids + b_ids):
            for hs in hstyles:
                hists[hs]['all-clones'].fill(mval)
            for key in (key_a, key_b):
                if key not in bigvals:
                    bigvals[key] = mval
                if mval > bigvals[key]:
                    bigvals[key] = mval
                if key not in smallvals:
                    smallvals[key] = mval
                if mval < smallvals[key]:
                    smallvals[key] = mval
        else:
            for hs in hstyles:
                hists[hs]['not'].fill(mval)

    if metric == 'logprob':
        bigkey = 'nearest'  # i.e. for logprob ratio, big values mean sequences are nearby
        smallkey = 'farthest'
    elif metric == 'naive_hfrac':
        bigkey = 'farthest'
        smallkey = 'nearest'
    for val in bigvals.values():
        for hs in hstyles:
            hists[hs][bigkey + '-clones'].fill(val)
    for val in smallvals.values():
        for hs in hstyles:
            hists[hs][smallkey + '-clones'].fill(val)

    ignore = False
    print ' ', metric, '----------------'
    for hs in hstyles:
        print '   ', hs
        fig, ax = plotting.mpl_init()
        if 'un-normed' not in hs:
            for k, h in hists[hs].items():
                h.normalize(include_overflows=not ignore, expect_empty=True)
                # print '    %20s %f' % (k, h.get_mean(ignore_overflows=ignore))  # NOTE ignoring overflows is kind of silly here!

        plots = {}
        plots['clonal'] = hists[hs]['all-clones'].mpl_plot(ax, ignore_overflows=ignore, label='clonal', alpha=0.7, linewidth=4, color='#6495ed')
        plots['not'] = hists[hs]['not'].mpl_plot(ax, ignore_overflows=ignore, label='non-clonal', linewidth=3, color='#2e8b57')  #linewidth=7, alpha=0.5)
        # plots['nearest'] = hists[hs]['nearest-clones'].mpl_plot(ax, ignore_overflows=ignore, label='nearest clones', linewidth=3)
        # plots['farthest'] = hists[hs]['farthest-clones'].mpl_plot(ax, ignore_overflows=ignore, label='farthest clones', linewidth=3, linestyle='--')
        if 'log' in hs:
            ax.set_yscale('log')
        xmin = hists[hs]['not'].xmin
        xmax = hists[hs]['not'].xmax
        delta = xmax - xmin
        leg_loc = None
        if metric == 'logprob':
            xlabel = 'log likelihood ratio'
        elif metric == 'naive_hfrac':
            leg_loc = (0.5, 0.7)
            xlabel = 'naive hamming fraction'
        plotting.mpl_finish(ax, plotdir + '/' + hs, plotname, title=plottitle, xlabel=xlabel, ylabel='counts' if 'un-normed' in hs else 'frequency', xbounds=[xmin - 0.03*delta, xmax + 0.03*delta], leg_loc=leg_loc)
        plotting.make_html(plotdir + '/' + hs)  # this'll overwrite itself a few times

# ----------------------------------------------------------------------------------------
def make_distance_plots(args, baseplotdir, label, n_leaves, mut_mult, cachefname, reco_info, metric):
    cachevals = {}
    singletons, pairs, triplets, quads = [], [], [], []
    with open(cachefname) as cachefile:
        reader = csv.DictReader(cachefile)
        # iline = 0
        for line in reader:
            if metric == 'logprob':
                if line[metric] == '':
                    continue
                cachevals[line['unique_ids']] = float(line['logprob'])
            elif metric == 'naive_hfrac':
                cachevals[line['unique_ids']] = -1. if line['naive_hfrac'] == '' else float(line['naive_hfrac'])  # we need the singletons, even if they don't have hfracs
            else:
                assert False

            unique_ids = line['unique_ids'].split(':')

            if not utils.from_same_event(reco_info, unique_ids):
                continue

            if len(unique_ids) == 1:
                singletons.append(line['unique_ids'])
            elif len(unique_ids) == 2:
                pairs.append(line['unique_ids'])  # use the string so it's obvious which order to use when looking in the cache
            elif len(unique_ids) == 3:
                triplets.append(line['unique_ids'])  # use the string so it's obvious which order to use when looking in the cache
            elif len(unique_ids) == 4:
                quads.append(line['unique_ids'])  # use the string so it's obvious which order to use when looking in the cache
            # iline += 1
            # if iline > 10:
            #     break

    plotdir = baseplotdir + '/distances'
    plotname = leafmutstr(args, n_leaves, mut_mult)

    print 'singletons'
    make_a_distance_plot(args, metric, itertools.combinations(singletons, 2), reco_info, cachevals, plotdir=plotdir + '/' + metric + '/singletons', plotname=plotname, plottitle=get_title(args, label, n_leaves, mut_mult) + ' (singletons)')

    print 'one pair one singleton'
    one_pair_one_singleton = []
    for ipair in range(len(pairs)):
        for ising in range(len(singletons)):
            one_pair_one_singleton.append((pairs[ipair], singletons[ising]))
    make_a_distance_plot(args, metric, one_pair_one_singleton, reco_info, cachevals, plotdir=plotdir + '/' + metric + '/one-pair-one-singleton', plotname=plotname, plottitle=get_title(args, label, n_leaves, mut_mult) + ' (pair + single)')

    print 'one triplet one singleton'
    one_triplet_one_singleton = []
    for itriplet in range(len(triplets)):
        for ising in range(len(singletons)):
            one_triplet_one_singleton.append((triplets[itriplet], singletons[ising]))
    make_a_distance_plot(args, metric, one_triplet_one_singleton, reco_info, cachevals, plotdir=plotdir + '/' + metric + '/one-triplet-one-singleton', plotname=plotname, plottitle=get_title(args, label, n_leaves, mut_mult) + ' (triple + single)')

    print 'one quad one singleton'
    one_quad_one_singleton = []
    for iquad in range(len(quads)):
        for ising in range(len(singletons)):
            one_quad_one_singleton.append((quads[iquad], singletons[ising]))
    make_a_distance_plot(args, metric, one_quad_one_singleton, reco_info, cachevals, plotdir=plotdir + '/' + metric + '/one-quad-one-singleton', plotname=plotname, plottitle=get_title(args, label, n_leaves, mut_mult) + ' (quad + single)')



    # print 'two pairs'
    # two_pairs = []
    # for ipair in range(len(pairs)):
    #     for jpair in range(ipair + 1, len(pairs)):
    #         two_pairs.append((pairs[ipair], pairs[jpair]))
    # make_a_distance_plot(args, metric, two_pairs, reco_info, cachevals, plotdir=plotdir + '/' + metric + '/two-pairs', plotname=plotname, plottitle=get_title(args, label, n_leaves, mut_mult) + ' (pair + pair)')

    # print 'two triplets'
    # two_triplets = []
    # for itriplet in range(len(triplets)):
    #     for jtriplet in range(itriplet + 1, len(triplets)):
    #         two_triplets.append((triplets[itriplet], triplets[jtriplet]))
    # make_a_distance_plot(args, metric, two_triplets, reco_info, cachevals, plotdir=plotdir + '/' + metric + '/two-triplets', plotname=plotname, plottitle=get_title(args, label, n_leaves, mut_mult) + ' (triplet + triplet)')

# ----------------------------------------------------------------------------------------
def write_all_plot_csvs(args, label):
    baseplotdir = os.getenv('www') + '/partis/clustering/' + label
    info = {k : {} for k in metrics + ['hists', 'partitions']}
    # hists, adj_mis, ccfs, partitions = {}, {}, {}, {}
    for n_leaves in args.n_leaf_list:
        for mut_mult in args.mutation_multipliers:
            print n_leaves, mut_mult
            write_each_plot_csvs(args, baseplotdir, label, n_leaves, mut_mult, info)

    check_call(['./bin/permissify-www', baseplotdir])

# ----------------------------------------------------------------------------------------
def write_each_plot_csvs(args, baseplotdir, label, n_leaves, mut_mult, info):
    for k in info:
        if n_leaves not in info[k]:
            info[k][n_leaves] = {}
        if mut_mult not in info[k][n_leaves]:
            info[k][n_leaves][mut_mult] = OrderedDict()
    this_info = {k : info[k][n_leaves][mut_mult] for k in info}

    plotdir = baseplotdir + '/subsets'
    if args.subset is not None:
        plotdir += '/subset-' + str(args.subset)
    if args.istartstop is not None:
        plotdir += '/istartstop-' + '-'.join([str(i) for i in args.istartstop])

    if args.data:
        seqfname = get_simfname(args, label, n_leaves, mut_mult).replace(leafmutstr(args, n_leaves, mut_mult), 'data')  # hackey hackey hackey
        simfbase = None
        csvdir = os.path.dirname(seqfname) + '/data'
        plotname = 'data'
        title = get_title(args, label, n_leaves, mut_mult)
    else:
        seqfname = get_simfname(args, label, n_leaves, mut_mult)
        simfbase = leafmutstr(args, n_leaves, mut_mult)
        csvdir = os.path.dirname(seqfname) + '/' + simfbase
        plotname = simfbase
        title = get_title(args, label, n_leaves, mut_mult)

    _, reco_info = seqfileopener.get_seqfile_info(seqfname, is_data=args.data)
    if args.count_distances:
        for metric in ['logprob', 'naive_hfrac']:
            make_distance_plots(args, plotdir, label, n_leaves, mut_mult, seqfname.replace('.csv', '-partition-cache.csv'), reco_info, metric)
        return

    rebin = None
    # if n_leaves > 10:
    #     rebin = 2

    # vollmers annotation (and true hists)
    parse_vollmers(args, this_info, seqfname, csvdir, reco_info, rebin=rebin)

    if not args.data:
        add_synthetic_partition_info(args, this_info, seqfname, csvdir, reco_info, rebin=rebin)

    if not args.no_mixcr:
        parse_mixcr(args, this_info, seqfname, csvdir)

    if not args.no_changeo:
        parse_changeo(args, label, n_leaves, mut_mult, this_info, simfbase, csvdir, rebin=rebin)

    # # partis stuff
    # for ptype in ['vsearch-', 'naive-hamming-', '']:
    #     parse_partis(args, ptype + 'partition', this_info, seqfname, csvdir, reco_info, rebin=rebin)

    log = 'xy'
    if not args.data and n_leaves <= 10:
        log = 'x'
    plotting.plot_cluster_size_hists(plotdir + '/cluster-size-distributions/' + plotname + '.svg', this_info['hists'], title=title, log=log)  #, xmax=n_leaves*6.01
    plotting.make_html(plotdir + '/cluster-size-distributions')  # this runs a bunch more times than it should
    if not args.no_similarity_matrices:  # they're kinda slow is all
        for meth1, meth2 in itertools.combinations(this_info['partitions'].keys(), 2):
            if '0.5' in meth1 or '0.5' in meth2:  # skip vollmers 0.5
                continue
            n_biggest_clusters = 40  # if args.data else 30)
            plotting.plot_cluster_similarity_matrix(plotdir + '/similarity-matrices/' + (meth1 + '-' + meth2).replace('partition ', ''), plotname, meth1, this_info['partitions'][meth1], meth2, this_info['partitions'][meth2], n_biggest_clusters=n_biggest_clusters, title=get_title(args, label, n_leaves, mut_mult))

# ----------------------------------------------------------------------------------------
def convert_adj_mi_and_co_to_plottable(args, valdict, mut_mult_to_use):
    plotvals = OrderedDict()
    for n_leaves in args.n_leaf_list:
        for meth, (val, err) in valdict[n_leaves][mut_mult_to_use].items():
            if meth not in plotvals:
                plotvals[meth] = OrderedDict()
            plotvals[meth][n_leaves] = val, err
    return plotvals

# ----------------------------------------------------------------------------------------
def compare_subsets(args, label):
    baseplotdir = os.getenv('www') + '/partis/clustering/' + label
    info = {k : {} for k in metrics + ['hists', ]}
    for n_leaves in args.n_leaf_list:
        print '%d leaves' % n_leaves
        for mut_mult in args.mutation_multipliers:
            print '  %.1f mutation' % mut_mult
            compare_subsets_for_each_leafmut(args, baseplotdir, label, n_leaves, mut_mult, info)

    if not args.data and args.plot_mean_of_subsets:
        for mut_mult in args.mutation_multipliers:
            for metric in metrics:
                plotvals = convert_adj_mi_and_co_to_plottable(args, info[metric], mut_mult)
                plotting.plot_adj_mi_and_co(plotvals, mut_mult, baseplotdir + '/means-over-subsets/metrics', metric, xvar='n_leaves', title='%dx mutation' % mut_mult)

    check_call(['./bin/permissify-www', baseplotdir])
    plotting.make_html(baseplotdir + '/means-over-subsets/metrics')

# ----------------------------------------------------------------------------------------
def compare_subsets_for_each_leafmut(args, baseplotdir, label, n_leaves, mut_mult, info):
    for k in info:
        if n_leaves not in info[k]:
            info[k][n_leaves] = {}
        if mut_mult not in info[k][n_leaves]:
            info[k][n_leaves][mut_mult] = OrderedDict()
    this_info = {k : info[k][n_leaves][mut_mult] for k in info}

    def get_histfname(subdir, method):
        if args.data:
            return subdir + '/data/hists/' + method + '.csv'
        else:
            return subdir + '/' + leafmutstr(args, n_leaves, mut_mult) + '/hists/' + method + '.csv'

    basedir = args.fsdir + '/' + label
    expected_methods = ['vollmers-0.9', 'mixcr', 'changeo', 'vsearch-partition', 'naive-hamming-partition', 'partition']
    for misfrac in [0.1, 0.9]:
        for mistype in ['singletons', 'reassign']:
            vname = 'misassign-%.2f-%s' % (misfrac, mistype)
            expected_methods.append(vname)

    if args.no_mixcr:
        expected_methods.remove('mixcr')
    if args.no_changeo:
        expected_methods.remove('changeo')
    if not args.data:
        expected_methods.insert(0, 'true')

    if args.n_subsets is not None:
        subdirs = [basedir + '/subset-' + str(isub) for isub in range(args.n_subsets)]
    elif args.istartstoplist is not None:
        subdirs = [basedir + '/istartstop-' + str(istartstop[0]) + '-' + str(istartstop[1]) for istartstop in args.istartstoplist]
        nseq_list = [istartstop[1] - istartstop[0] for istartstop in args.istartstoplist]
    else:
        assert False

    per_subset_info = {k : OrderedDict() for k in metrics + ['hists', ]}
    for metric in per_subset_info:
        if n_leaves == 1 and metric == 'adj_mi':
            continue
        for method in expected_methods:
            if metric != 'hists' and (args.data or method == 'true'):
                continue
            if method not in per_subset_info[metric]:
                per_subset_info[metric][method] = []
            for subdir in subdirs:
                if metric == 'hists':
                    hist = Hist(fname=get_histfname(subdir, method))
                    per_subset_info[metric][method].append(hist)
                else:
                    fname = subdir + '/' + leafmutstr(args, n_leaves, mut_mult) + '/' + metric+ '/' + method + '.csv'
                    value = read_float_val(fname, metric)
                    per_subset_info[metric][method].append(value)

    # fill this_info with hists of mean over subsets, and plot them
    if args.plot_mean_of_subsets:
        for method in expected_methods:
            this_info['hists'][method] = plotting.make_mean_hist(per_subset_info['hists'][method])
        cluster_size_plotdir = baseplotdir + '/means-over-subsets/cluster-size-distributions'
        log = 'xy'
        if args.data:
            title = get_title(args, label, n_leaves, mut_mult)
            plotfname = cluster_size_plotdir + '/data.svg'
            xmax = 10
        else:
            title = get_title(args, label, n_leaves, mut_mult)
            plotfname = cluster_size_plotdir + '/' + leafmutstr(args, n_leaves, mut_mult) + '.svg'
            xmax = n_leaves*6.01
            if n_leaves <= 10:
                log = 'x'
        plotting.plot_cluster_size_hists(plotfname, this_info['hists'], title=title, xmax=xmax, log=log)
        plotting.make_html(cluster_size_plotdir)

    if not args.data:
        for metric in metrics:
            print '   ', metric
            if not args.plot_mean_of_subsets:  # if we're not averaging over the subsets for each leafmut, then we want to plot adj_mi (and whatnot) as a function of subset (presumably each subset is a different size)
                plotvals = OrderedDict()
                for method, values in per_subset_info[metric].items():
                    plotvals[method] = OrderedDict([(nseqs , (val, 0.)) for nseqs, val in zip(nseq_list, values)])
                metric_plotdir = os.getenv('www') + '/partis/clustering/' + label + '/plots-vs-subsets/metrics'
                plotting.plot_adj_mi_and_co(plotvals, mut_mult, metric_plotdir, metric, xvar='nseqs', title=get_title(args, label, n_leaves, mut_mult))
                plotting.make_html(metric_plotdir)
            for meth, vals in per_subset_info[metric].items():
                mean = numpy.mean(vals)
                if mean == -1.:
                    continue
                std = numpy.std(vals)
                this_info[metric][meth] = (mean, std)
                print '        %30s %.3f +/- %.3f' % (meth, mean, std)

# ----------------------------------------------------------------------------------------
def get_misassigned_adj_mis(simfname, misassign_fraction, nseq_list, error_type):
    input_info, reco_info = seqfileopener.get_seqfile_info(simfname, is_data=False)
    n_reps = 1
    uid_list = input_info.keys()
    new_partitions = {}
    for nseqs in nseq_list:
        for irep in range(n_reps):  # repeat <nreps> times
            istart = irep * nseqs
            istop = istart + nseqs
            uids = uid_list[istart : istop]
            true_partition = utils.get_true_partition(reco_info, ids=uids)
            new_partition = utils.generate_incorrect_partition(true_partition, misassign_fraction, error_type=error_type)
            # new_partition = utils.generate_incorrect_partition(true_partition, misassign_fraction, error_type='singletons')
            new_partitions[nseqs] = new_partition
    return {nseqs : utils.adjusted_mutual_information(new_partitions[nseqs], utils.get_true_partition(reco_info, ids=new_partitions[nseqs].keys())) for nseqs in nseq_list}

# ----------------------------------------------------------------------------------------
def output_exists(args, outfname):
    if os.path.exists(outfname):
        if os.stat(outfname).st_size == 0:
            print '                      deleting zero length %s' % outfname
            os.remove(outfname)
            return False
        elif args.overwrite:
            print '                      overwriting %s' % outfname
            if os.path.isdir(outfname):
                raise Exception('output %s is a directory, rm it by hand' % outfname)
            else:
                os.remove(outfname)
            return False
        else:
            print '                      output exists, skipping (%s)' % outfname
            return True
    else:
        return False

# ----------------------------------------------------------------------------------------
def run_changeo(args, label, n_leaves, mut_mult, seqfname):
    def untar_imgt(imgtdir):
        tar_cmd = 'mkdir ' + imgtdir + ';'
        tar_cmd += ' tar Jxvf ' + imgtdir + '.txz --exclude=\'IMGT_HighV-QUEST_individual_files_folder/*\' -C ' + imgtdir
        check_call(tar_cmd, shell=True)

    imgtdir = get_changeo_outdir(args, label, n_leaves, mut_mult)
    if os.path.isdir(imgtdir):
        print '                      already untar\'d into %s' % imgtdir
    else:
        if os.path.exists(imgtdir + '.txz'):
            untar_imgt(imgtdir)
        else:
            print '   hmm... imgtdir not there... maybe we only have the subsets'

    if args.subset is not None:
        subset_dir = imgtdir + '/subset-' + str(args.subset)
        if not os.path.exists(subset_dir):
            os.makedirs(subset_dir)
            tsvfnames = glob.glob(imgtdir + '/*.txt')
            check_call(['cp', '-v', imgtdir + '/11_Parameters.txt', subset_dir + '/'])
            tsvfnames.remove(imgtdir + '/11_Parameters.txt')
            tsvfnames.remove(imgtdir + '/README.txt')
            input_info, reco_info = seqfileopener.get_seqfile_info(seqfname, is_data=False)
            subset_ids = input_info.keys()
            utils.subset_files(subset_ids, tsvfnames, subset_dir)
        imgtdir = subset_dir
    if args.istartstop is not None:
        subset_dir = imgtdir + '/istartstop_' + '_'.join([str(i) for i in args.istartstop])
        if os.path.exists(subset_dir + '.txz'):
            untar_imgt(subset_dir)
        elif not os.path.exists(subset_dir):
            os.makedirs(subset_dir)
            tsvfnames = glob.glob(imgtdir + '/*.txt')
            check_call(['cp', '-v', imgtdir + '/11_Parameters.txt', subset_dir + '/'])
            tsvfnames.remove(imgtdir + '/11_Parameters.txt')
            tsvfnames.remove(imgtdir + '/README.txt')
            input_info, reco_info = seqfileopener.get_seqfile_info(seqfname, is_data=args.data)
            subset_ids = input_info.keys()
            utils.subset_files(subset_ids, tsvfnames, subset_dir)
        imgtdir = subset_dir

    def run(cmdstr):
        print 'RUN %s' % cmdstr
        check_call(cmdstr.split(), env=os.environ)

    resultfname = imgtdir + changeorandomcrapstr
    if output_exists(args, resultfname):
        return

    fastafname = os.path.splitext(seqfname)[0] + '.fasta'
    utils.csv_to_fasta(seqfname, outfname=fastafname)  #, name_column='name' if args.data else 'unique_id', seq_column='nucleotide' if args.data else 'seq')
    bindir = '/home/dralph/work/changeo/changeo/bin'
    os.environ['PYTHONPATH'] = bindir.replace('/bin', '')
    start = time.time()
    cmd = bindir + '/MakeDb.py imgt -i ' + imgtdir + ' -s ' + fastafname + ' --failed'
    # cmd = bindir + '/MakeDb.py imgt -h'
    run(cmd)
    cmd = bindir + '/ParseDb.py select -d ' + imgtdir + '_db-pass.tab'
    if args.data:
        cmd += ' -f FUNCTIONAL -u T'
    else:  # on simulation we don't want to skip any (I'm not forbidding stop codons in simulation)
        cmd += ' -f FUNCTIONAL -u T F'
    run(cmd)
    # cmd = bindir + '/DefineClones.py bygroup -d ' + imgtdir + '_db-pass_parse-select.tab --act first --model m1n --dist 7'
    cmd = bindir + '/DefineClones.py bygroup -d ' + imgtdir + '_db-pass_parse-select.tab --model hs1f --norm len --act set --dist 0.2'
    run(cmd)
    print '        changeo time: %.3f' % (time.time()-start)

    # read changeo's output and toss it into a csv
    input_info, reco_info = seqfileopener.get_seqfile_info(seqfname, is_data=args.data)
    id_clusters = {}  # map from cluster id to list of seq ids
    with open(resultfname) as chfile:
        reader = csv.DictReader(chfile, delimiter='\t')
        for line in reader:
            clid = line['CLONE']
            uid = line['SEQUENCE_ID']
            if clid not in id_clusters:
                id_clusters[clid] = []
            id_clusters[clid].append(uid)

    partition = [ids for ids in id_clusters.values()]
    # these_hists['changeo'] = plotting.get_cluster_size_hist(partition)
    if not args.data:
        true_partition = utils.get_true_partition(reco_info)
        subset_of_true_partition = utils.remove_missing_uids_from_true_partition(true_partition, partition)
        print 'removed from true: %.3f' % utils.adjusted_mutual_information(subset_of_true_partition, partition)

        partition_with_uids_added = utils.add_missing_uids_as_singletons_to_inferred_partition(utils.get_true_partition(reco_info), partition)
        print 'added to inferred: %.3f' % utils.adjusted_mutual_information(true_partition, partition_with_uids_added)
        assert False  # need to work out why changeo is filtering out so many seqs, and decide how to treat them if I can't fix it

        write_float_val(imgtdir + '-adj_mi.csv', adj_mi, 'adj_mi')
        ccfs = utils.correct_cluster_fractions(partition, reco_info)
        write_float_val(imgtdir + '-ccf_under.csv', ccfs[0], 'ccf_under')
        write_float_val(imgtdir + '-ccf_over.csv', ccfs[1], 'ccf_over')

# ----------------------------------------------------------------------------------------
def run_mixcr(args, label, n_leaves, mut_mult, seqfname):
    binary = '/home/dralph/work/mixcr/mixcr-1.2/mixcr'
    mixcr_workdir = get_program_workdir(args, 'mixcr', label, n_leaves, mut_mult)
    if not os.path.exists(mixcr_workdir):
        os.makedirs(mixcr_workdir)

    # fastafname = os.path.splitext(seqfname)[0] + '.fasta'
    infname = mixcr_workdir + '/' + os.path.basename(os.path.splitext(seqfname)[0] + '.fasta')
    outfname = os.path.splitext(seqfname)[0] + '-mixcr.tsv'
    if output_exists(args, outfname):
        return

    # check_call(['./bin/csv2fasta', seqfname])
    utils.csv_to_fasta(seqfname, outfname=infname, n_max_lines=args.n_to_partition)  #, name_column='name' if args.data else 'unique_id', seq_column='nucleotide' if args.data else 'seq'
    # check_call('head -n' + str(2*args.n_to_partition) + ' ' + fastafname + ' >' + infname, shell=True)
    # os.remove(seqfname.replace('.csv', '.fa'))

    def run(cmdstr):
        print 'RUN %s' % cmdstr
        check_call(cmdstr.split())

    start = time.time()
    cmd = binary + ' align -f --loci IGH ' + infname + ' ' + infname.replace('.fasta', '.vdjca')
    run(cmd)
    cmd = binary + ' assemble -f ' + infname.replace('.fasta', '.vdjca') + ' ' + infname.replace('.fasta', '.clns')
    run(cmd)
    cmd = binary + ' exportClones ' + infname.replace('.fasta', '.clns') + ' ' + infname.replace('.fasta', '.txt')
    run(cmd)
    print '        mixcr time: %.3f' % (time.time()-start)
    check_call(['cp', '-v', infname.replace('.fasta', '.txt'), outfname])


# ----------------------------------------------------------------------------------------
def run_igscueal(args, label, n_leaves, mut_mult, seqfname):
    igscueal_dir = '/home/dralph/work/IgSCUEAL'
    # outfname = os.path.splitext(seqfname)[0] + '-igscueal.tsv'
    # if output_exists(args, outfname):
    #     return
    workdir = get_program_workdir(args, 'igscueal', label, n_leaves, mut_mult)

    infname = workdir + '/' + os.path.basename(os.path.splitext(seqfname)[0] + '.fasta')

    if not os.path.exists(workdir):
        os.makedirs(workdir)

    utils.csv_to_fasta(seqfname, outfname=infname, n_max_lines=args.n_to_partition)  #, name_column='name' if args.data else 'unique_id', seq_column='nucleotide' if args.data else 'seq'
    # write cfg file (.bf)
    sed_cmd = 'sed'
    replacements = {'igscueal_dir' : igscueal_dir,
                    'input_fname' : infname,
                    'results_fname' : workdir + '/results.tsv',
                    'rearrangement_fname' : workdir + '/rearrangement.tsv',
                    'tree_assignment_fname' : workdir + '/tree_assignment.tsv'}
    for pattern, replacement in replacements.items():
        sed_cmd += ' -e \'s@xxx-' + pattern + '-xxx@' + replacement + '@\''
    template_cfgfname = igscueal_dir + '/TopLevel/MPIScreenFASTA.bf'
    cfgfname = workdir + '/cfg.bf'
    sed_cmd += ' ' + template_cfgfname + ' >' + cfgfname
    check_call(sed_cmd, shell=True)

    # cmd = 'salloc -N 3 mpirun -np 3 /home/dralph/work/hyphy/hyphy-master/HYPHYMPI ' + cfgfname
    # srun --mpi=openmpi
    cmd = 'srun --exclude=data/gizmod.txt mpirun -np 2 /home/dralph/work/hyphy/hyphy-master/HYPHYMPI ' + cfgfname

    ntot = int(check_output(['wc', '-l', infname]).split()[0]) / 2
    n_procs = max(1, int(float(ntot) / 10))
    n_per_proc = int(float(ntot) / n_procs)  # NOTE ignores remainders, i.e. last few sequences
    workdirs = []
    start = time.time()
    procs = []
    for iproc in range(n_procs):
        workdirs.append(workdir + '/igs-' + str(iproc))
        if not os.path.exists(workdirs[-1]):
            os.makedirs(workdirs[-1])

        if len(procs) - procs.count(None) > 500:  # can't have more open files than something like this
            print '        too many procs (len %d    none %d)' % (len(procs), procs.count(None))
            procs.append(None)
            continue

        suboutfname = replacements['results_fname'].replace(workdir, workdirs[-1])
        if os.path.exists(suboutfname) and os.stat(suboutfname).st_size != 0:
            print '    %d already there (%s)' % (iproc, suboutfname)
            procs.append(None)
            continue

        check_call(['cp', cfgfname, workdirs[-1] + '/'])
        check_call(['sed', '-i', 's@' + workdir + '@' + workdirs[-1] + '@', workdirs[-1] + '/' + os.path.basename(cfgfname)])

        subinfname = workdirs[-1] + '/' + os.path.basename(infname)
        istart = 2 * iproc * n_per_proc + 1  # NOTE sed indexing (one-indexed with inclusive bounds), and factor of two for fasta file
        istop = istart + 2 * n_per_proc - 1
        check_call('sed -n \'' + str(istart) + ',' + str(istop) + ' p\' ' + infname + '>' + subinfname, shell=True)

        print '     starting %d' % iproc
        procs.append(Popen(cmd.replace(workdir, workdirs[-1]).split(), stdout=PIPE, stderr=PIPE))
        # procs.append(Popen(['sleep', '10']))

    while procs.count(None) < len(procs):
        for iproc in range(n_procs):
            if procs[iproc] is not None and procs[iproc].poll() is not None:  # it's finished
                stdout, stderr = procs[iproc].communicate()
                print '\nproc %d' % iproc
                print 'out----\n', stdout, '\n-----'
                print 'err----\n', stderr, '\n-----'
                procs[iproc] = None
            time.sleep(0.1)
    print '      igscueal time: %.3f' % (time.time()-start)

# ----------------------------------------------------------------------------------------
def slice_file(args, csv_infname, csv_outfname):  # not necessarily csv
    if os.path.exists(csv_outfname):
        utils.csv_to_fasta(csv_outfname)  #, name_column='name' if args.data else 'unique_id', seq_column='nucleotide' if args.data else 'seq')
        print '      slicefile exists %s' % csv_outfname
        return
    print '      subsetting %d seqs with indices %d --> %d' % (args.istartstop[1] - args.istartstop[0], args.istartstop[0], args.istartstop[1])
    if not os.path.exists(os.path.dirname(csv_outfname)):
        os.makedirs(os.path.dirname(csv_outfname))
    if '.csv' in csv_infname:  # if it's actually a csv
        remove_csv_infname = False
        check_call('head -n1 ' + csv_infname + ' >' + csv_outfname, shell=True)
        check_call('sed -n \'' + str(args.istartstop[0] + 2) + ',' + str(args.istartstop[1] + 1) + ' p\' ' + csv_infname + '>>' + csv_outfname, shell=True)  # NOTE conversion from standard zero indexing to sed inclusive one-indexing (and +1 for header line)
        if remove_csv_infname:
            assert '/dralph/' in csv_infname
            os.remove(csv_infname)
    elif '.fa' in csv_infname:
        input_info, _ = seqfileopener.get_seqfile_info(csv_infname, is_data=True)
        with open(csv_outfname, 'w') as outfile:
            writer = csv.DictWriter(outfile, ('unique_id', 'seq'))
            writer.writeheader()
            iseq = -1
            for line in input_info.values():  # hackey, but it's an ordered dict so it should be ok
                iseq += 1
                if iseq < args.istartstop[0]:
                    continue
                if iseq >= args.istartstop[1]:
                    break
                writer.writerow({'unique_id' : line['unique_id'], 'seq' : line['seq']})
        # print 'sed -n \'' + str(2*args.istartstop[0] + 1) + ',' + str(2*args.istartstop[1] + 1) + ' p\' ' + csv_infname + '>>' + csv_outfname
        # check_call('sed -n \'' + str(2*args.istartstop[0] + 1) + ',' + str(2*args.istartstop[1] + 1) + ' p\' ' + csv_infname + '>>' + csv_outfname, shell=True)  # NOTE conversion from standard zero indexing to sed inclusive one-indexing (and multiply by two for fasta file)

# ----------------------------------------------------------------------------------------
def get_seqfile(args, datafname, label, n_leaves, mut_mult):

    if args.data:
        if args.istartstop is None:
            seqfname = datafname
        else:
            subfname = args.fsdir + '/' + label + '/istartstop-' + '-'.join([str(i) for i in args.istartstop]) + '/data.csv'
            slice_file(args, datafname, subfname)
            seqfname = subfname
    else:
        if not args.data:
            assert n_leaves is not None and mut_mult is not None
        simfname = get_simfname(args, label, n_leaves, mut_mult, no_subset=True)

        if args.subset is not None:
            ntot = int(check_output(['wc', '-l', simfname]).split()[0]) - 1
            subsimfname = simfname.replace(label + '/', label + '/subset-' + str(args.subset) + '/')
            if os.path.exists(subsimfname):
                print '      subset file exists %s' % subsimfname
            else:
                print '      subsetting %d / %d' % (args.subset, args.n_subsets)
                if not os.path.exists(os.path.dirname(subsimfname)):
                    os.makedirs(os.path.dirname(subsimfname))
                check_call('head -n1 ' + simfname + ' >' + subsimfname, shell=True)
                n_per_subset = int(float(ntot) / args.n_subsets)  # NOTE ignores remainders, i.e. last few sequences
                istart = args.subset * n_per_subset + 2  # NOTE sed indexing (one-indexed with inclusive bounds). Also note extra +1 to avoid header
                istop = istart + n_per_subset - 1
                check_call('sed -n \'' + str(istart) + ',' + str(istop) + ' p\' ' + simfname + '>>' + subsimfname, shell=True)
            simfname = subsimfname

        if args.istartstop is not None:
            subsimfname = simfname.replace(label + '/', label + '/istartstop-' + '-'.join([str(i) for i in args.istartstop]) + '/')
            slice_file(args, simfname, subsimfname)
            simfname = subsimfname

        seqfname = simfname

    return seqfname

# ----------------------------------------------------------------------------------------
def execute(args, action, datafname, label, n_leaves, mut_mult, procs):
    cmd = './bin/run-driver.py --label ' + label + ' --action '
    if 'partition' in action:
        cmd += ' partition'
    else:
        cmd += ' ' + action
    cmd += ' --stashdir ' + args.fsdir + ' --old-style-dir-structure'

    extras = []
    seqfname = get_seqfile(args, datafname, label, n_leaves, mut_mult)
    if args.data:
        cmd += ' --datafname ' + seqfname + ' --is-data'
        if args.dataset == 'adaptive':
            extras += ['--skip-unproductive', ]
    else:
        cmd += ' --simfname ' + seqfname

    def get_outputname():
        if args.data:
            return get_outdirname(args, label) + '/data-' + action + '.csv'
        else:
            return ('-' + action).join(os.path.splitext(seqfname))

    n_procs, n_fewer_procs = 1, 1
    if action == 'cache-data-parameters':
        if output_exists(args, args.fsdir + '/' + label + '/data'):
            return
        extras += ['--n-max-queries', + args.n_data_to_cache]
        n_procs = max(1, args.n_data_to_cache / 500)
        n_fewer_procs = min(500, args.n_data_to_cache / 2000)
    elif action == 'simulate':
        if output_exists(args, seqfname):
            return
        extras += ['--n-sim-events', int(float(args.n_sim_seqs) / n_leaves)]
        extras += ['--n-leaves', n_leaves, '--mutation-multiplier', mut_mult]
        if args.indels:
            extras += ['--indel-frequency', 0.5]
        if args.lonely_leaves:
            extras += ['--constant-number-of-leaves', ]
        n_procs = 10
    elif action == 'cache-simu-parameters':
        if output_exists(args, seqfname.replace('.csv', '')):
            return
        n_procs = 20
        n_fewer_procs = min(500, args.n_sim_seqs / 2000)
    elif action == 'partition':
        outfname = get_outputname()
        if output_exists(args, outfname):
            return
        cmd += ' --outfname ' + outfname
        extras += ['--n-max-queries', args.n_to_partition]
        if args.count_distances:
            extras += ['--cache-naive-hfracs', '--persistent-cachefname', ('-cache').join(os.path.splitext(outfname))]  # '--n-partition-steps', 1,
        n_procs = max(1, args.n_to_partition / 100)
        n_fewer_procs = min(500, args.n_to_partition / 2000)
    elif action == 'naive-hamming-partition':
        outfname = get_outputname()
        if output_exists(args, outfname):
            return
        cmd += ' --outfname ' + outfname
        extras += ['--n-max-queries', args.n_to_partition, '--naive-hamming']
        n_procs = max(1, args.n_to_partition / 200)
    elif action == 'vsearch-partition':
        outfname = get_outputname()
        if output_exists(args, outfname):
            return
        cmd += ' --outfname ' + outfname
        extras += ['--n-max-queries', args.n_to_partition, '--naive-vsearch']
        n_procs = max(1, args.n_to_partition / 100)  # only used for ighutil step
    elif action == 'run-viterbi':
        outfname = get_outputname()
        if output_exists(args, outfname):
            return
        cmd += ' --outfname ' + outfname
        extras += ['--annotation-clustering', 'vollmers', '--annotation-clustering-thresholds', '0.5:0.9']
        extras += ['--n-max-queries', args.n_to_partition]
        n_procs = max(1, args.n_to_partition / 50)
    elif action == 'run-changeo':
        run_changeo(args, label, n_leaves, mut_mult, seqfname)
        return
    elif action == 'run-mixcr':
        run_mixcr(args, label, n_leaves, mut_mult, seqfname)
        return
    elif action == 'run-igscueal':
        run_igscueal(args, label, n_leaves, mut_mult, seqfname)
        return
    else:
        raise Exception('bad action %s' % action)

    # cmd += ' --plotdir ' + os.getenv('www') + '/partis'
    if n_procs > 500:
        print 'reducing n_procs %d --> %d' % (n_procs, 500)
        n_procs = 500
    n_proc_str = str(n_procs)
    extras += ['--workdir', args.fsdir.replace('_output', '_tmp') + '/' + str(random.randint(0, 99999))]
    if n_procs > 10:
        n_fewer_procs = max(1, n_fewer_procs)
        n_proc_str += ':' + str(n_fewer_procs)

    extras += ['--n-procs', n_proc_str]

    cmd += baseutils.get_extra_str(extras)
    print '   ' + cmd
    # return
    # check_call(cmd.split())
    # return
    if args.data:
        logbase = args.fsdir + '/' + label + '/_logs/data-' + action
    else:
        logbase = args.fsdir + '/' + label + '/_logs/' + leafmutstr(args, n_leaves, mut_mult) + '-' + action
    if args.subset is not None:
        logbase = logbase.replace('_logs/', '_logs/subset-' + str(args.subset) + '/')
    if args.istartstop is not None:
        logbase = logbase.replace('_logs/', '_logs/istartstop-' + '-'.join([str(i) for i in args.istartstop]) + '/')
    if not os.path.exists(os.path.dirname(logbase)):
        os.makedirs(os.path.dirname(logbase))
    proc = Popen(cmd.split(), stdout=open(logbase + '.out', 'w'), stderr=open(logbase + '.err', 'w'))
    procs.append(proc)
    # time.sleep(30)  # 300sec = 5min

