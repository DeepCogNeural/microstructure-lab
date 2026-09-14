# Agent entrypoint

Pull branch `advisor/application-packaging-closeout-20260914` and complete the application-packaging closeout.

```bash
git fetch origin
git switch advisor/application-packaging-closeout-20260914
git pull --ff-only origin advisor/application-packaging-closeout-20260914
cat docs/LOCAL_AGENT_APPLICATION_PACKAGING.md
```

Treat `docs/CLAIMS_REGISTRY_SEED.md` as the conservative claim gate. Do not run new research experiments or tune existing models. Complete the recruiter-facing README/documentation cleanup plus the branch-only resume/interview packets specified in the handoff, run tests/privacy checks, create `docs/LOCAL_AGENT_APPLICATION_PACKAGING_COMPLETION.md`, and push this branch only. Do not merge `main`.
