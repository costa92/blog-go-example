# Roadmap: tally

## Phases

- [x] **Phase 1: Line and word counts** - Count lines and words from stdin
- [ ] **Phase 2: Frequent words report** - Optional report of the most frequent words
- [ ] **Phase 3: JSON output** - Machine-readable output mode

## Phase Details

### Phase 1: Line and word counts
**Goal**: Print `lines=N words=M` for stdin
**Depends on**: Nothing (first phase)
**Success Criteria** (what must be TRUE):
  1. `echo "a b" | tally` prints `lines=1 words=2`
**Plans**: 1 plan (done)

### Phase 2: Frequent words report
**Goal**: Users can see which words occur most often
**Depends on**: Phase 1
**Success Criteria** (what must be TRUE):
  1. A flag selects how many top words to print
  2. Default output is unchanged
**Plans**: TBD

### Phase 3: JSON output
**Goal**: `-json` prints the same data as a JSON object
**Depends on**: Phase 2
**Success Criteria** (what must be TRUE):
  1. Output parses with `jq`
**Plans**: TBD
