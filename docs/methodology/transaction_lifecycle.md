# Transaction Lifecycle History

## Purpose

Transaction status is historical information, not merely a mutable property of
a transaction record.

A financing may progress through states such as:

- announced;
- marketing;
- launched;
- priced;
- allocated;
- settled;
- postponed;
- withdrawn;
- cancelled.

The platform therefore represents lifecycle history as evidence-backed status
events.

`TransactionRecord` remains the stable financing-event identity.

Lifecycle events describe what happened to that financing event over time.

## Lifecycle Event Identifier

Lifecycle events use permanent identifiers in the `TLE...` namespace.

For example:

`TLE000000001`

The identifier is non-semantic.

It does not encode:

- transaction;
- status;
- date;
- product;
- issuer.

## Event Structure

Each lifecycle event contains:

- permanent lifecycle-event ID;
- canonical transaction ID;
- controlled transaction status;
- effective date;
- intra-day event order;
- one or more evidence IDs;
- optional notes.

The evidence chain is:

Source
→ Evidence
→ Transaction Lifecycle Event

## Effective Date

`effective_date` represents the date on which the lifecycle state became
effective for the transaction.

It is not automatically:

- source publication date;
- source document date;
- source access date;
- analyst ingestion date.

Those dates remain governed separately in `SourceRecord`.

If a source published later describes an earlier status change, the lifecycle
event should retain the status's actual effective date where that date is
supported.

## Intra-Day Event Order

Capital-markets transactions can pass through multiple lifecycle states on the
same calendar date.

For example:

LAUNCHED
→ PRICED

may occur on the same day.

The platform does not fabricate an exact clock time when only the date is
known.

Instead, `event_order` records the known relative sequence of lifecycle events
within the same transaction and effective date.

`event_order`:

- is a positive integer;
- is scoped to one transaction and effective date;
- must be unique within that transaction/date combination.

The number is structural ordering metadata, not an assertion that an event
occurred at a particular time of day.

## Event Identity and Duplicate Control

Within one transaction and effective date, `event_order` identifies the
lifecycle event's position in the known sequence.

The combination of:

- transaction ID;
- effective date;
- event order

must therefore be unique.

The same status may legitimately recur on the same effective date when an
intervening event changes the transaction state.

For example:

LAUNCHED
→ POSTPONED
→ LAUNCHED

may be represented with event orders 1, 2, and 3 on the same date when that
sequence is supported by evidence.

If several sources support the same lifecycle event, their evidence IDs should
be consolidated on the same event record rather than creating parallel rows
for the same ordering slot.

## Status Derivation

Current transaction status is derived from lifecycle history.

The latest event is selected by:

1. effective date;
2. intra-day event order.

Historical status can be derived using an `as_of_date` cut-off.

Because the current lifecycle model uses date-level rather than clock-time
precision, an `as_of_date` includes all ordered lifecycle events effective on
that date. The derived status is therefore the latest known status through the
end of that effective date.

If no lifecycle event exists at or before the requested date, status is
unknown rather than inferred.

The canonical `TransactionRecord` therefore does not require a mutable current
status field.

## No Universal Transition Graph

The generic lifecycle layer does not impose one universal state-transition
graph.

Capital-markets execution paths differ by product and circumstance.

For example:

ANNOUNCED
→ MARKETING
→ LAUNCHED
→ PRICED

may be common, but not universal.

A transaction may also experience:

LAUNCHED
→ POSTPONED
→ LAUNCHED
→ PRICED

where transaction-identity methodology determines that the later launch is a
continuation of the same financing event.

Likewise, some products may omit states that are meaningful in other products.

The generic layer therefore records supported chronology without assuming all
transactions traverse identical states.

Product-specific validators may later impose narrower requirements where
appropriate.

## Postponed, Withdrawn, and Cancelled

`POSTPONED`, `WITHDRAWN`, and `CANCELLED` remain distinct controlled statuses.

Their precise analytical interpretation should be based on the transaction's
facts and source evidence.

The lifecycle layer does not automatically assume that all three have identical
terminal behavior.

If a financing reappears after a withdrawal or cancellation, transaction
identity must be assessed explicitly:

- continuation of the existing transaction; or
- a new financing event.

That determination should not be made merely by overwriting the prior status.

## Preservation of Failed Execution

Postponed, withdrawn, and cancelled transactions remain part of canonical
history.

They must not be deleted simply because execution did not complete.

These events are analytically valuable for:

- execution-window assessment;
- market-condition analysis;
- precedent failure rates;
- investor-risk appetite;
- issuer timing analysis.

## Corrections and Conflicts

Source disagreement about lifecycle facts should not be resolved by silently
rewriting history.

Where evidence conflicts, the underlying source and evidence records should be
preserved and the discrepancy handled through the platform's review and
exception-control process.

A later methodology extension may introduce explicit event supersession if
real correction cases demonstrate that it is required.

The initial model deliberately avoids adding correction mechanics before actual
use cases justify them.

## Persistence Boundary

`TransactionLifecycleEventRecord` defines canonical lifecycle semantics.

It is not yet the database persistence model.

A later storage implementation should preserve:

- permanent lifecycle IDs;
- transaction references;
- evidence references;
- unique transaction/date/order slots;
- deterministic historical status derivation.
