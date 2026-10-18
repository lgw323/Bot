# 21. Target Repository Structure

```text
discordbot/
├── pyproject.toml                 # runtime/tool policy; lockfile 별도
├── src/discordbot/
│   ├── composition/
│   │   ├── config.py              # typed, immutable configuration
│   │   ├── discord_app.py         # discord process wiring only
│   │   └── watch_app.py           # web process wiring only
│   ├── platform/
│   │   ├── errors.py              # cross-context error vocabulary
│   │   ├── tasks.py               # TaskSupervisor
│   │   ├── health.py
│   │   └── telemetry.py
│   ├── music/
│   │   ├── domain/                # queue/state/retry policy/value objects
│   │   ├── application/           # use cases, actor messages
│   │   ├── ports/                 # playback/metadata/repositories/clock
│   │   └── adapters/              # Discord UI/voice, yt-dlp, FFmpeg, SQLite
│   ├── summary/
│   │   ├── domain/
│   │   ├── application/
│   │   ├── ports/
│   │   └── adapters/              # Discord capture/render, Gemini
│   ├── engagement/
│   │   ├── domain/                # XP/birthday/date policies
│   │   ├── application/
│   │   ├── ports/
│   │   └── adapters/              # Discord and SQLite
│   ├── watch/
│   │   ├── domain/                # session/playlist/expiry state machine
│   │   ├── application/
│   │   ├── ports/
│   │   └── adapters/              # HTTP/WS, SQLite, oEmbed, loopback admin
│   └── operations/
│       ├── application/
│       ├── ports/
│       └── adapters/              # backup/release/admin notifier
├── migrations/                    # ordered, checksummed, reversible policy
├── deploy/
│   ├── systemd/                   # tracked unit/timer templates
│   ├── scripts/                   # locked, atomic release commands
│   └── runbooks/
├── tests/
│   ├── characterization/
│   ├── unit/
│   ├── integration/
│   ├── contracts/
│   ├── concurrency/
│   ├── failure/
│   └── e2e/
└── docs/
    ├── product/
    ├── architecture/
    ├── adr/
    └── operations/
```

## Dependency rules

```text
composition ──> adapters ──> application ──> domain
                         └──> ports <───────┘
platform(errors/types) may be used inward; vendor SDKs remain in adapters.
```

- domain은 다른 context의 adapter/domain과 vendor/framework를 import하지 않는다.
- application은 자기 domain과 port, 제한된 platform type만 의존한다.
- adapter는 port를 구현하되 business decision을 하지 않는다.
- Discord/FastAPI inbound adapter는 repository/SDK outbound adapter를 직접 호출하지 않는다.
- context 간 호출은 versioned application contract/event로 하며 table을 공유 API로 쓰지 않는다.
- composition만 concrete implementation과 lifecycle 순서를 안다.
- migration/deploy code는 application package import 시 실행되지 않는다.
- architecture tests가 금지 import와 cycle을 CI에서 검사한다.

## Public contracts

각 context는 command/query DTO, result/error, port protocol, event schema만 export한다. internal
module과 Discord object/SQLite row/vendor response는 경계 밖으로 내보내지 않는다. WebSocket,
HTTP, snapshot, backup compatibility schema는 versioned contract fixture를 갖는다.

## Packaging/deployment

두 entrypoint(`discord-bot`, `watch-web`)가 같은 locked wheel을 사용하고 process별 config,
service user/permission, health endpoint를 가진다. release directory는 immutable하고 state/data는
release 밖의 명시 경로다. 정확한 Python/package pin과 OS artifact checksum을 release manifest에
기록한다.
