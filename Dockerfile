FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies including Python + GStreamer Python bindings
RUN apt-get update && apt-get install -y \
    git cmake build-essential \
    curl unzip libssl-dev \
    libcurl4-openssl-dev liblog4cplus-dev \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    python3 python3-pip python3-venv \
    python3-gi gir1.2-gstreamer-1.0 \
    pkg-config \
    ca-certificates \
    awscli \
    && rm -rf /var/lib/apt/lists/*


WORKDIR /opt

# Clone the C++ SDK
RUN git clone --recursive https://github.com/awslabs/amazon-kinesis-video-streams-producer-sdk-cpp.git

WORKDIR /opt/amazon-kinesis-video-streams-producer-sdk-cpp

# Build the GStreamer plugin only
RUN mkdir -p build && cd build && \
    cmake .. -DBUILD_GSTREAMER_PLUGIN=ON -DBUILD_DEPENDENCIES=ON -DBUILD_TEST=OFF && \
    make -j$(nproc)

# Set environment for GStreamer to find AWS plugin & libraries
ENV GST_PLUGIN_PATH=/opt/amazon-kinesis-video-streams-producer-sdk-cpp/build
ENV LD_LIBRARY_PATH=/opt/amazon-kinesis-video-streams-producer-sdk-cpp/open-source/local/lib

# Copy Python test script into container
COPY test_gstreamer.py /opt/test_gstreamer.py

# Run the test during build
RUN python3 /opt/test_gstreamer.py

# Default to Python REPL
CMD ["python3"]
