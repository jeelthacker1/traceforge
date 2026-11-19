"""Bounded safe workload, restricted to the fixed local demonstration gateway."""
import argparse
import time

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=30)
    parser.add_argument('--failures', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.count <= 10000:
        parser.error('count must be between 1 and 10000')
    with httpx.Client(base_url='http://demo-api-gateway:8000', timeout=10) as client:
        for i in range(args.count):
            path = '/login?fail=true' if args.failures else ['/browse', '/login', '/orders'][i % 3]
            response = client.get(path)
            print(i, path, response.status_code, flush=True)
            time.sleep(0.1)


if __name__ == '__main__':
    main()
