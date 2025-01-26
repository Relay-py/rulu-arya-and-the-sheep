from openai import OpenAI
import sys

def test_openai_api():
    try:
        client = OpenAI(api_key='')
        
        print("1. Successfully initialized OpenAI client")
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'Hello, API test successful!' if you can read this."}
            ],
            max_tokens=50
        )
        
        print("2. Successfully made API call")
        print("\nAPI Response:")
        print(response.choices[0].message.content)
        print("\nAPI test completed successfully!")
        return True
        
    except Exception as e:
        print("\nError occurred during API test:")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        print("\nFull error details:")
        print(e)
        return False

if __name__ == "__main__":
    print("Starting OpenAI API test...\n")
    success = test_openai_api()
    if not success:
        sys.exit(1) 