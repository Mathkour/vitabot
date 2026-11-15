# Keeping Bitbucket and GitHub in sync

The vitabot source code lives in two places:

| Host | URL | Role |
|------|-----|------|
| Bitbucket | `git@ssh.bitbucket.org:vitacareonline/vitabot.git` | Main copy (fetch and pull come from here) |
| GitHub | `https://github.com/Mathkour/vitabot.git` | Mirror (receives every push) |

`origin` has **two push URLs**, so a single `git push` updates both hosts.

## Everyday use

Nothing extra is needed:

```bash
git add <files>
git commit -m "message"
git push origin main            # goes to Bitbucket AND GitHub
git push origin <branch-name>   # works for any branch
```

The output shows one result for each host. Check that both succeeded. A line such as `To https://github.com/...` with no errors means GitHub got the push.

## One-time setup on a new machine (or after a fresh clone)

This setup is stored in the local `.git/config`, so you have to repeat it on every machine and in every clone.

```bash
git clone git@ssh.bitbucket.org:vitacareonline/vitabot.git
cd vitabot

# Add both push URLs. Bitbucket must be added explicitly, because adding
# the first push URL replaces the default one.
git remote set-url --add --push origin git@ssh.bitbucket.org:vitacareonline/vitabot.git
git remote set-url --add --push origin https://github.com/Mathkour/vitabot.git

# Verify: you should see 1 fetch line and 2 push lines
git remote -v
```

Expected output:

```
origin  git@ssh.bitbucket.org:vitacareonline/vitabot.git (fetch)
origin  git@ssh.bitbucket.org:vitacareonline/vitabot.git (push)
origin  https://github.com/Mathkour/vitabot.git (push)
```

### Login

- **Bitbucket:** SSH key `~/.ssh/id_ed25519` (already registered on Bitbucket).
- **GitHub:** HTTPS through Git Credential Manager. On the first push, Windows opens a GitHub sign-in window and remembers it after that.
  - If you'd rather use SSH: add `~/.ssh/id_ed25519.pub` under GitHub → Settings → SSH and GPG keys, then change the GitHub push URL:
    ```bash
    git remote set-url --delete --push origin https://github.com/Mathkour/vitabot.git
    git remote set-url --add --push origin git@github.com:Mathkour/vitabot.git
    ssh -T git@github.com   # should greet you by username
    ```

## Checking that both hosts match

```bash
git fetch origin
git rev-parse main
git ls-remote https://github.com/Mathkour/vitabot.git main
```

The two hashes must be the same. If GitHub is behind, run `git push origin main` again.

## Rules

1. **Never commit directly on GitHub.** That includes web edits and merged pull requests. Those changes don't reach Bitbucket, and the two copies drift apart. Make all changes locally, or on Bitbucket, then push.
2. **Pushes from a machine without this setup only reach Bitbucket.** That includes teammates and CI. Afterwards, from a configured machine, run `git pull` and then `git push origin main` to bring GitHub up to date.
3. **If one host rejects a push** (for example a network failure or an expired login), the other host may still have succeeded. Fix the cause and push again. Git only sends what's missing.

## Undoing the setup

```bash
git remote set-url --delete --push origin https://github.com/Mathkour/vitabot.git
```

`origin` then pushes only to Bitbucket again.
