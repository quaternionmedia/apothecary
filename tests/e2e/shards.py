"""How the browser suite is cut into shards (``--shard K/N``, tests/e2e/conftest.py)."""


def shard_of(files: dict, shards: int) -> dict:
    """Each file's shard, whole files only: the heaviest first onto the lightest shard.

    ``files`` maps a file to its seconds. A file's tests stay together and in order,
    because the walkthroughs and the ring's tests build on the steps before them.
    """
    load = [0.0] * shards
    placed = {}
    for name, seconds in sorted(files.items(), key=lambda kv: (-kv[1], kv[0])):
        lightest = min(range(shards), key=lambda i: (load[i], i))
        placed[name] = lightest
        load[lightest] += seconds
    return placed
