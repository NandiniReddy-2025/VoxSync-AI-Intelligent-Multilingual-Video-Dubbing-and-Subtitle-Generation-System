import asyncio
import os
import subprocess
import edge_tts
from config import FFMPEG_EXE

async def generate():
    speech_text = "Welcome to VoxSync AI. This is an intelligent video dubbing test."
    speech_file = "sample_speech.mp3"
    comm = edge_tts.Communicate(speech_text, "en-US-JennyNeural")
    await comm.save(speech_file)

    video_file = "sample_test.mp4"
    cmd = [
        FFMPEG_EXE,
        "-f", "lavfi",
        "-i", "testsrc=duration=5:size=640x360:rate=25",
        "-i", speech_file,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-shortest",
        "-pix_fmt", "yuv420p",
        video_file,
        "-y"
    ]
    subprocess.run(cmd, check=True)
    print(f"Sample test video created at: {os.path.abspath(video_file)}")
    if os.path.exists(speech_file):
        os.remove(speech_file)

if __name__ == "__main__":
    asyncio.run(generate())
