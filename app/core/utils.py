import re

def parse_llm_response_to_number(response: str) -> str:
    """
    Finds the first number in the LLM's response string and intelligently
    converts it to an int or float, returning it as a string.
    """
    cleaned_response = response.strip()

    match = re.search(r'[-+]?\d*\.\d+|\d+', cleaned_response)
    if not match:
        return cleaned_response

    number_str = match.group(0)

    try:
        float_val = float(number_str)
        if float_val.is_integer():
            return str(int(float_val))
        else:
            return str(float_val)
    except ValueError:
        return cleaned_response 