"""Explicit child entrypoint. Importing does not import gTTS or perform work."""


def main() -> None:
    import sys
    from gtts import gTTS

    if len(sys.argv) != 2 or not 0 < len(sys.argv[1]) <= 200:
        raise SystemExit(2)
    gTTS(text=sys.argv[1], lang="ko", timeout=(5, 10)).write_to_fp(sys.stdout.buffer)


if __name__ == "__main__":
    main()
