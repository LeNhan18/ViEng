import edge_tts
import asyncio

async def main():
    communicate = edge_tts.Communicate("Hello, this is a TOEIC listening test.", "en-US-AriaNeural")
    await communicate.save("output.mp3")

asyncio.run(main())
