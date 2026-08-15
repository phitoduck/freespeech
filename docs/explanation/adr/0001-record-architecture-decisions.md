# 1. Record architecture decisions

- Status: accepted
- Date: 2026-08-15

## Context

This is a prototype built to try out a way of working — BDD for the behaviours,
property-based testing for the guarantees, Diátaxis for the docs — as much as it
is built to read PDFs aloud. The reasoning is the deliverable. If only the code
survives, the experiment taught nothing.

## Decision

Record every decision that would be expensive to reverse as an ADR in
`docs/explanation/adr/`, in [MADR](https://adr.github.io/madr/) form. ADRs live
in the **Explanation** quadrant of the Diátaxis site, which is the one quadrant
with nothing executable to assert — it is where the "why" belongs.

An ADR is warranted when a choice constrains what can be built later. Choosing a
CSS colour is not an ADR. Choosing to derive word timings rather than measure
them is.

## Consequences

- The set of ADRs is small and each one is worth reading.
- The QRSPI phase documents in `.humanlayer/tasks/` capture the *process*;
  ADRs capture the *decisions*. They are different artefacts and both are kept.
- Superseding an ADR means writing a new one that references it, not editing the
  old one. The record is append-only.
