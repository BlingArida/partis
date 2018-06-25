FROM continuumio/anaconda

RUN apt-get update && apt-get install -y \
  build-essential \
  cmake \
  libgsl-dev \
  libncurses-dev \
  libxt6 \
  libboost-dev \
  libyaml-cpp-dev \
  libyaml-dev \
  libz-dev

RUN conda update -y conda
RUN conda install -y python=2.7
RUN conda install -y biopython pandas psutil pysam scons seaborn zlib pyyaml scikit-learn
RUN conda install -y -c biocore mafft
RUN pip install colored-traceback dendropy==3.12.3
RUN git clone https://github.com/psathyrella/partis.git
WORKDIR /partis
RUN ./bin/build.sh
CMD ./test/test.py --quick
