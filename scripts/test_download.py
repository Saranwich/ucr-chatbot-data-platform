import asyncio
import os
from linebot.v3.messaging import Configuration, AsyncApiClient, AsyncMessagingApiBlob
from dotenv import load_dotenv

load_dotenv()

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")

async def test_download():
    configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
    async with AsyncApiClient(configuration) as api_client:
        blob_api = AsyncMessagingApiBlob(api_client)
        message_id = "611792338792218625"
        try:
            print(f"Downloading {message_id}...")
            content = await blob_api.get_message_content(message_id)
            if not os.path.exists("uploads"):
                os.makedirs("uploads")
            with open(f"uploads/{message_id}.jpg", "wb") as f:
                f.write(content)
            print("✅ Success!")
        except Exception as e:
            print(f"❌ Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_download())
