# Wellness Avatar

The wellness bot loads a VRM avatar from `/avatars/wellness.vrm`.

## Getting a VRM

Two options — both produce a `.vrm` file natively, no conversion.

**A. VRoid Hub (browse + download an existing avatar)**
1. Visit https://hub.vroid.com/ and browse community avatars. Filter for ones with a "Download permitted" / "Use license" tag that allows embedding. A calm/wellness vibe is recommended for the bot.
2. Click the avatar → **Download** → save as `.vrm`.

**B. VRoid Studio (build your own — desktop app)**
1. Install VRoid Studio (free) from https://vroid.com/en/studio
2. Customize a half-body or full-body model.
3. **Export → VRM** (the app produces `.vrm` directly).

After either path:
- Rename the downloaded file to `wellness.vrm`.
- Place it at `frontend/public/avatars/wellness.vrm`.

The file is git-ignored — each environment supplies its own. The frontend will render a "Loading avatar..." card if the file is missing, then fall back to text-only chat.
