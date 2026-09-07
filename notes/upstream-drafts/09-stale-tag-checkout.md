Title: Warn when the selected ref is far behind the default branch (tag checkout without --vcs-ref)

## Summary

`copier copy https://github.com/org/template.git dest` **without `--vcs-ref`** checks out the latest git **tag**, not the default branch (documented, but easy to miss). For repositories that were forked or renamed, the latest tag can point at a long-abandoned ancestor of the template. The user is then silently asked the *old* questionnaire and receives the *old* generated files, believing they used the current template. This exact trap produced two real bug reports against our template in one week.

## Current behavior (real case)

Our repository is a fork that inherited upstream tags; the newest tag (`5.4.0`, tagged by the upstream project) predates every template feature added since the fork:

```console
$ copier copy https://github.com/kasi-x/python-copier-template.git ./dest
# ... copies from the 5.4.0 tag content ...
Copying from template version 5.4.0.post45.dev0+cbb65076
```

Symptoms our users hit, both caused by this checkout choice alone:

- `ValueError: Invalid choice for 'docs_type': 'zensical' is not in ['README', 'sphinx']` — the *old* tag's choice list (the current template offers zensical).
- Copier asks for `component_owner` — a question that only exists in the old tag's `copier.yml`, not in the current template.

`git show 5.4.0:copier.yml` confirms both. The only signal the user gets is the `Copying from template version 5.4.0...` line, which does not convey "this is 44 commits behind `main` and not what the repository README describes".

## Expected behavior

One or both of:

1. **Docs**: state the tag-selection default prominently wherever `copier copy` is introduced for URL-based generation ("without `--vcs-ref`, the latest tag is used, not the default branch").
2. **Warning**: when the resolved ref is a tag that is N commits behind the default branch, print a warning such as:

   ```
   Warning: using tag 5.4.0, which is 44 commits behind the default branch main.
   Pass --vcs-ref=main to use the branch tip.
   ```

   The clone already exists at that point, so detecting the distance is one `git rev-list --count <default-branch>..<tag>` call.

## Environment

Copier 9.18.1, Python 3.11.14, Linux (Ubuntu)
