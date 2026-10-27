# Security and privacy

Carwatch is a local research prototype with no remote authentication. Keep its server bound to 127.0.0.1. Do not publish it through a tunnel or expose it to a network without adding an authentication and authorization design.

Treat uploaded videos as untrusted media. Keep Python, OpenCV, PyTorch and ffmpeg patched. This app is not a sandbox for hostile codec payloads. Only load model checkpoints obtained from a trusted source. Custom checkpoints use PyTorch's weights-only loader plus a model-card checksum; checksums detect mismatched files, not a malicious author who controls both files.

Source recordings retain their original audio. Derived clips are silent. Source videos, snapshots, features, reviews and models persist in the local data directory until deleted. No encryption or user access separation is implemented by this app.

Camera access requires the user's Start action. It runs in a separate process with a parent-enforced time limit and explicit Stop. A hardware failure or process kill may lose the most recent unsaved observation. No software result establishes safety.

Optional ntfy notifications require environment configuration, confirmation of a private topic and explicit enablement when starting a live session. Keep tokens outside Git. The sender requires verified HTTPS and rejects redirects; it sends only fixed cue text and its UTC observation time. Journals omit the token, destination and media. Configure the service's topic permissions separately: a token or the local private-topic confirmation flag does not prove anonymous access is denied. The notification service and its mobile push providers have their own retention and access policies. See [notification setup](docs/NOTIFICATIONS.md). No real endpoint is configured by the repository.

For a suspected vulnerability, use [GitHub's private vulnerability report](https://github.com/aaryapatel09/carwatch/security/advisories/new). Include the affected commit, a minimal reproduction using synthetic data, and the potential impact. Do not put private recordings, credentials, or sensitive exploit details in a public issue. There is no guaranteed response time; do not rely on this prototype for safety-critical use.
