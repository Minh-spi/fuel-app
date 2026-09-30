"""Local launcher for the same Flask application deployed to Vercel."""
import argparse
import os
from app import app

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', '8000')))
    # Accepted for old local scripts; sync is always explicit in this architecture.
    parser.add_argument('--no-auto-sync', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)

if __name__ == '__main__':
    main()
