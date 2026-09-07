import os
import ffmpeg

with open('test.srt', 'w', encoding='utf-8') as f:
    f.write('1\n00:00:00,000 --> 00:00:01,000\nTest\n')

# The correct way to pass an absolute Windows path to ffmpeg-python subtitles filter
# It handles its own escaping for filter syntax, so we only need to convert backslashes to forward slashes.
# Wait, actually, let's just pass the relative path since we are in the same or parent directory?
# No, let's try just forward slashes first.
srt_path = os.path.abspath('test.srt').replace('\\', '/')
print('PATH:', srt_path)

# But ffmpeg subtitles filter DOES need the colon (C:/) to be escaped, otherwise it thinks C is the filter name.
# ffmpeg-python escapes values if they are passed as kwargs (e.g. filename='C:/...').
# Let's test passing filename=srt_path instead of positional argument!

v = ffmpeg.input('color=c=black:s=1280x720:d=1', f='lavfi').video.filter('subtitles', filename=srt_path)
out = ffmpeg.output(v, 'out.mp4', **{'vcodec': 'libx264'}).overwrite_output()

print("COMPILADO:")
print(ffmpeg.compile(out))

try:
    out.run(capture_stdout=True, capture_stderr=True)
    print('SUCCESS')
except ffmpeg.Error as e:
    stderr = e.stderr.decode('utf-8', errors='ignore') if e.stderr else ""
    print('ERROR:\n' + stderr)
