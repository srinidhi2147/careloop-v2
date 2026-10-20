import os, base64, sys
from openai import OpenAI

client = OpenAI(
    base_url="https://api.tokenfactory.us-north1.nebius.com/v1/",
    api_key=os.environ["NEBIUS_API_KEY"],
   )
MODEL = "nvidia/Nemotron-3.5-Super-VL"

   # 1) text test
r = client.chat.completions.create(
    model=MODEL,
    messages=[{"role": "user", "content": "Say hello in five words."}],
)
print("TEXT:", r.choices[0].message.content)

# 2) image test (pass a prescription photo path)
if len(sys.argv) > 1:
    b64 = base64.b64encode(open(sys.argv[1], "rb").read()).decode()
    r = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": "List each medicine, strength and timing as JSON only."},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
        ]}],
    )
print("IMAGE:", r.choices[0].message.content)