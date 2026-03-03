import requests
import json
import time

def test_paddleocr_service():
    print('Testing PaddleOCR Service...')
    
    # Load test request
    with open('test_request.json', 'r') as f:
        test_data = json.load(f)
    
    try:
        # Try to connect to service
        response = requests.post(
            'http://localhost:8001/detect-layout',
            json=test_data,
            timeout=5
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f'✅ Service responded successfully')
            print(f'  Status: {response.status_code}')
            print(f'  Regions detected: {len(result.get("regions", []))}')
            print(f'  Processing time: {result.get("processing_time_ms", 0)}ms')
            
            # Check bounding boxes
            regions = result.get('regions', [])
            for i, region in enumerate(regions):
                bbox = region.get('bbox', [])
                print(f'  Region {i}: type={region.get("type")}, bbox={bbox}, confidence={region.get("confidence")}')
            
            return True
        else:
            print(f'❌ Service error: {response.status_code}')
            print(f'  Response: {response.text}')
            return False
            
    except requests.exceptions.ConnectionError:
        print('❌ Service not running on localhost:8001')
        print('  Start the service with: cd services/paddleocr-service && uvicorn app.main:app --host 0.0.0.0 --port 8001')
        return False
    except Exception as e:
        print(f'❌ Test error: {e}')
        return False

if __name__ == '__main__':
    test_paddleocr_service()