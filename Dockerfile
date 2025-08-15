# =============================
# 1️⃣ Build stage
# =============================
FROM ubuntu:20.04 AS build

ENV DEBIAN_FRONTEND=noninteractive

# Install build dependencies
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
    pkg-config \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt

# Clone AWS Kinesis Video Streams C++ SDK
RUN git clone --recursive https://github.com/awslabs/amazon-kinesis-video-streams-producer-sdk-cpp.git

# Build only the GStreamer plugin
WORKDIR /opt/amazon-kinesis-video-streams-producer-sdk-cpp
RUN mkdir -p build
WORKDIR /opt/amazon-kinesis-video-streams-producer-sdk-cpp/build
RUN cmake .. -DBUILD_GSTREAMER_PLUGIN=ON -DBUILD_DEPENDENCIES=ON -DBUILD_TEST=OFF
RUN make -j2

# =============================
# 2️⃣ Runtime stage
# =============================
FROM ubuntu:20.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive

# Install only runtime dependencies (Python + GStreamer runtime libs)
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv \
    python3-gi gir1.2-gstreamer-1.0 \
    gstreamer1.0-libav \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    libgstreamer1.0-0 \
    libgstreamer-plugins-base1.0-0 \
    libcurl4 \
    ca-certificates \
    awscli \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip3 install --no-cache-dir \
    gql[requests] \
    requests \
    boto3 \
    opencv-python-headless

WORKDIR /opt

# Copy AWS plugin & libs from build stage
COPY --from=build /opt/amazon-kinesis-video-streams-producer-sdk-cpp/build /opt/amazon-kinesis-video-streams-producer-sdk-cpp/build
COPY --from=build /opt/amazon-kinesis-video-streams-producer-sdk-cpp/open-source/local/lib /opt/amazon-kinesis-video-streams-producer-sdk-cpp/open-source/local/lib

# Set environment variables so GStreamer finds the AWS plugin
ENV GST_PLUGIN_PATH=/opt/amazon-kinesis-video-streams-producer-sdk-cpp/build
ENV LD_LIBRARY_PATH=/opt/amazon-kinesis-video-streams-producer-sdk-cpp/open-source/local/lib

# Copy Python GStreamer test script
#COPY test_gstreamer.py /opt/test_gstreamer.py
COPY main_with_threading.py /opt/main.py

# Copy the log configuration one directory above the plugin
COPY kvs_log_configuration /opt/kvs_log_configuration

# Make sure it's readable
RUN chmod 644 /opt/kvs_log_configuration



ENV PYTHONUNBUFFERED=1
#ENV AWS_KVS_LOG_LEVEL=2
ENV AWS_KVS_LOG_LEVEL=0
#ENV GST_DEBUG=kvssink:5

#ENV GST_DEBUG=kvssink:5,rtsp*:5
# Completely suppress GStreamer debug output
ENV GST_DEBUG=0
ENV KVS_LOG_LEVEL=ERROR
ENV KVS_LOG_CONFIGURATION_FILE=/opt/kvs_log_configuration

ENTRYPOINT ["python3", "/opt/main.py"]
CMD []
