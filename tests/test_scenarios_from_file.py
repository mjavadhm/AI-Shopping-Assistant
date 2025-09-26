import json
import pytest
from fastapi.testclient import TestClient
from app.main import app
from collections import defaultdict

client = TestClient(app)

# --- Test Configuration ---
# Specify the maximum number of test cases to run for each scenario.
# A value of 0 or leaving a scenario out means all its test cases will be run.
TEST_LIMITS = {
    "SCENARIO_1_DIRECT_SEARCH": 2,
    "SCENARIO_3_SELLER_INFO": 2,
    "SCENARIO_5_COMPARISON": 2,
    "SCENARIO_6_IMAGE_OBJECT_DETECTION": 0, # 0 means no limit
}

def load_test_cases():
    try:
        with open("my_tests.json", "r", encoding="utf-8") as f:
            all_tests = json.load(f)
    except FileNotFoundError:
        pytest.fail("The file my_tests.json was not found. Please ensure it is in the project root.")
    except json.JSONDecodeError:
        pytest.fail("The file my_tests.json is not a valid JSON.")

    allowed_scenarios = [
        "SCENARIO_1_DIRECT_SEARCH",
        "SCENARIO_3_SELLER_INFO",
        "SCENARIO_5_COMPARISON",
        "SCENARIO_6_IMAGE_OBJECT_DETECTION",
    ]

    grouped_tests = defaultdict(list)
    for test in all_tests:
        scenario = test.get("scenario")
        if scenario in allowed_scenarios:
            grouped_tests[scenario].append(test)

    # Apply limits and flatten the list
    limited_tests = []
    for scenario, tests in grouped_tests.items():
        limit = TEST_LIMITS.get(scenario)
        if limit and limit > 0:
            limited_tests.extend(tests[:limit])
        else:
            limited_tests.extend(tests)

    if not limited_tests:
        pytest.fail("No valid test cases were found for the specified scenarios in my_tests.json.")
        
    return limited_tests

@pytest.mark.parametrize("test_case", load_test_cases())
def test_real_scenario_from_file(test_case):
    request_data = test_case["request"]
    expected_response_data = test_case["response"]
    scenario = test_case["scenario"]

    response = client.post("/chat", json=request_data)

    assert response.status_code == 200, f"Server error for chat_id {request_data['chat_id']}. Response: {response.text}"
    
    actual_response = response.json()

    print(f"\nTesting Scenario: {scenario} for chat_id: {request_data['chat_id']}")
    print(f"--> Actual Response: {actual_response}")
    print(f"--> Expected Response Keys: {expected_response_data}")

    if scenario in ["SCENARIO_1_DIRECT_SEARCH", "SCENARIO_5_COMPARISON", "SCENARIO_6_IMAGE_OBJECT_DETECTION"]:
        assert actual_response["base_random_keys"] == expected_response_data["base_random_keys"], \
            f"For scenario {scenario}, 'base_random_keys' did not match."

    elif scenario == "SCENARIO_3_SELLER_INFO":
         assert actual_response["message"] is not None, \
            f"For scenario {scenario}, the response message should not be null."
    
    assert actual_response["member_random_keys"] == expected_response_data["member_random_keys"], \
        "'member_random_keys' did not match."