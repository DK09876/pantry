import os
from google import genai
from google.genai.errors import APIError

client = genai.Client()

print("==================================================")
print(" Fetching Available Models from Gemini API...")
print("==================================================\n")

working_models = []

try:
  # Query the API directly for all models associated with your API key
  models = list(client.models.list())

  print(f"Found {len(models)} model definitions.\n")
  print("Testing 'generate_content' support on candidates:\n")

  for m in models:
    # Extract clean model ID (e.g., 'gemini-2.0-flash' or 'models/gemini-2.0-flash')
    model_id = m.name.replace("models/", "") if m.name else str(m)

    # Test basic content generation
    try:
      response = client.models.generate_content(
          model=model_id, contents="Reply with 'OK'"
      )
      print(f"  [SUCCESS] {model_id}")
      working_models.append(model_id)
    except APIError as e:
      print(f"  [FAILED]  {model_id} -> {e.code} ({e.message})")
    except Exception as e:
      print(f"  [FAILED]  {model_id} -> {e}")

except Exception as e:
  print(f"Error querying API: {e}")

print("\n==================================================")
if working_models:
  print(" Working Models for your script:")
  for wm in working_models:
    print(f"  -> '{wm}'")
else:
  print(" No models succeeded. Check GEMINI_API_KEY permissions.")
print("==================================================")