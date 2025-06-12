#!/usr/bin/env python3
import requests
import json

# Your NEW Qdrant Cloud configuration
QDRANT_URL = "https://bad7e720-f630-4fe4-a36d-9e7f85ae7503.europe-west3-0.gcp.cloud.qdrant.io:6333"
QDRANT_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.o0-1435PBNpbvrb4AvciyNGW9XhYQc8SmP76Dcmk7s0"

def test_qdrant_connection():
    """Test new Qdrant Cloud instance"""
    print("🔧 Testing NEW Qdrant Cloud Instance")
    print("=" * 60)
    print(f"URL: {QDRANT_URL}")
    print(f"API Key: {QDRANT_API_KEY[:30]}...")
    print("=" * 60)
    
    # Test different authentication methods for JWT tokens
    auth_methods = [
        ("api-key header", {"api-key": QDRANT_API_KEY}),
        ("Authorization Bearer", {"Authorization": f"Bearer {QDRANT_API_KEY}"}),
        ("Authorization Token", {"Authorization": f"Token {QDRANT_API_KEY}"}),
        ("x-api-key header", {"x-api-key": QDRANT_API_KEY}),
    ]
    
    endpoints = ["/health", "/collections", "/cluster"]
    
    success_count = 0
    
    for endpoint in endpoints:
        print(f"\n📡 Testing endpoint: {endpoint}")
        print("-" * 40)
        
        for auth_name, headers in auth_methods:
            try:
                url = f"{QDRANT_URL}{endpoint}"
                response = requests.get(url, headers=headers, timeout=15)
                
                status = response.status_code
                print(f"  {auth_name:<20}: {status}", end="")
                
                if status == 200:
                    print(" ✅ SUCCESS!")
                    success_count += 1
                    try:
                        data = response.json()
                        print(f"    📄 Response: {json.dumps(data, indent=2)}")
                    except:
                        print(f"    📄 Response: {response.text}")
                    
                    # If collections endpoint works, try to list collections
                    if endpoint == "/collections" and auth_name == "api-key header":
                        print(f"    🎯 Using {auth_name} for collections - THIS IS YOUR WORKING CONFIG!")
                        return True, headers
                        
                elif status == 401:
                    print(" 🔐 Unauthorized")
                elif status == 403:
                    print(" ❌ Forbidden")
                elif status == 404:
                    print(" 🔍 Not Found")
                else:
                    print(f" ⚠️  Status {status}: {response.text[:50]}")
                    
            except requests.exceptions.Timeout:
                print(f"  {auth_name:<20}: ⏰ Timeout")
            except requests.exceptions.ConnectionError:
                print(f"  {auth_name:<20}: 🔌 Connection Error")
            except Exception as e:
                print(f"  {auth_name:<20}: ❌ {str(e)[:30]}")
    
    return success_count > 0, None

def test_create_collection(working_headers):
    """Test creating a collection"""
    print(f"\n🏗️  Testing Collection Creation")
    print("-" * 40)
    
    try:
        url = f"{QDRANT_URL}/collections/test_collection"
        
        payload = {
            "vectors": {
                "size": 768,
                "distance": "Cosine"
            }
        }
        
        response = requests.put(url, headers=working_headers, json=payload, timeout=15)
        print(f"Create collection status: {response.status_code}")
        
        if response.status_code in [200, 201]:
            print("✅ Collection created successfully!")
            return True
        elif response.status_code == 409:
            print("✅ Collection already exists!")
            return True
        else:
            print(f"❌ Failed to create collection: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Collection creation error: {e}")
        return False

def main():
    print("🚀 QDRANT CLOUD CONNECTION TEST")
    print("=" * 60)
    
    success, working_headers = test_qdrant_connection()
    
    if success:
        print(f"\n🎉 SUCCESS! Qdrant Cloud is working!")
        print("=" * 60)
        
        if working_headers:
            print(f"✅ Working authentication method found!")
            print(f"📝 Use these headers: {working_headers}")
            
            # Test collection operations
            test_create_collection(working_headers)
            
        print(f"\n📋 UPDATE YOUR DOCKER COMPOSE:")
        print(f"   QDRANT_URL={QDRANT_URL}")
        print(f"   QDRANT_API_KEY={QDRANT_API_KEY}")
        
    else:
        print(f"\n❌ No working configuration found")
        print("🔍 Check your Qdrant Cloud dashboard for cluster status")

if __name__ == "__main__":
    main()