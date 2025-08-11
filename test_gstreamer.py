#!/usr/bin/env python3
import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst

# Initialize GStreamer
Gst.init(None)
print("✅ GStreamer initialized.")

# Get list of loaded plugins
registry = Gst.Registry.get()
plugins = [p.get_name() for p in registry.get_plugin_list()]

# Check for AWS plugin
if any("kvssink" in p for p in plugins):
    print("✅ AWS Kinesis GStreamer plugin detected!")
else:
    print("❌ AWS Kinesis GStreamer plugin NOT found!")

print("Loaded plugins:", plugins)
