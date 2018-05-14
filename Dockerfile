FROM continuumio/anaconda

RUN apt-get update && apt-get install -y \
  build-essential \
  cmake \
  libgsl-dev \
  libncurses-dev \
  libz-dev

RUN conda install python=2.7
RUN conda install -y biopython pandas psutil pysam scons seaborn zlib
RUN conda install -y -c biocore mafft
RUN pip install colored-traceback dendropy==3.12.3
RUN git clone https://github.com/psathyrella/partis.git
WORKDIR /partis
RUN ./bin/build.sh
RUN conda install -y r-essentials \
    && unset R_LIBS_SITE \
    && R --vanilla --slave -e 'install.packages("TreeSim", repos="http://cran.rstudio.com/")'
CMD ./test/test.py --quick
