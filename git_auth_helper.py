#!/usr/bin/env python
"""
Git credential helper to force authentication as karthikeyareddy07.
This reads stdin for credential operations and responds with proper auth.
"""
import sys
import os

def handle_credential_request():
    """Handle git credential protocol requests."""
    lines = []
    while True:
        try:
            line = input()
            if not line:
                break
            lines.append(line)
        except EOFError:
            break
    
    # Parse request
    request = {}
    for line in lines:
        if '=' in line:
            key, value = line.split('=', 1)
            request[key] = value
    
    # Check if this is a github.com request
    if request.get('host') == 'github.com' and request.get('protocol') == 'https':
        # Output credentials for karthikeyareddy07
        print("username=karthikeyareddy07")
        print("password=")  # Will be filled by git credential manager with PAT
    
    return 0

if __name__ == '__main__':
    if len(sys.argv) > 1:
        operation = sys.argv[1]
        if operation in ['get', 'store', 'erase']:
            sys.exit(handle_credential_request())
    sys.exit(0)
