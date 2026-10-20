"""Run the seed build from the IDE: the same as `python -m thought_seeds <args>`.

Example run configuration arguments: --sources=parti --raw=raw --out=out --fetch=1 --limit=200"""
import sys

from thought_seeds.build import main

if __name__ == "__main__":
    sys.exit(main())
