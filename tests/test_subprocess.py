import os
import subprocess

with open('test.srt', 'w', encoding='utf-8') as f:
    f.write('1\n00:00:00,000 --> 00:00:01,000\nTest\n')

srt_path = os.path.abspath('test.srt')
# FFmpeg subtitles filter rules:
# 1. Backslashes to forward slashes
# 2. Escape colon
srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
print("ESCAPED:", srt_escaped)

# For subprocess, we pass exactly the string we want FFmpeg to parse.
# If we wrap it in single quotes in the filter graph, it helps with spaces.
# Wait, if we use single quotes around the path, maybe we don't need to escape colon?
# Let's test with single quotes and colon escaped:
filter_complex = f"color=c=black:s=1280x720:d=1[v];[v]subtitles='{srt_escaped}'"

cmd = [
    "ffmpeg",
    "-f", "lavfi",
    "-i", "color=c=black:s=1280x720:d=1",
    "-filter_complex", f"[0:v]subtitles='{srt_escaped}'[v]",
    "-map", "[v]",
    "-vcodec", "libx264",
    "-y",
    "out2.mp4"
]

print("CMD:", " ".join(cmd))

result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode == 0:
    print("SUCCESS")
else:
    print("ERROR:")
    print(result.stderr)
