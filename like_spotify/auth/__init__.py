"""Auth helpers shared across hosts/extensions.

Currently only Google's installed-app OAuth lives here; Spotify keeps
its PKCE flow inside the `spotify` extension because it's also the
provider. If a second non-provider OAuth flow appears (Last.fm, etc.)
the pattern is set.
"""
