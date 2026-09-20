"""An in-memory, append-only account ledger core.

No web layer, no persistence, no UI, no database -- by design. The whole thing
is a pure function from an event stream to a set of projections, which is what
makes it testable without a single fixture file.

    from ledger.engine import Engine
    from ledger.scenario import ACCOUNTS, build_events

    engine = Engine(ACCOUNTS, build_events()).run()
    engine.book.closing_balance("ACC-001", day=2, known_through=5)   # AED -370.00
    engine.book.closing_balance("ACC-001", day=2)                    # AED  225.00

Module map:

    money     Money and Currency. Precision is a property of the currency.
    records   The frozen record types and the append-only log.
    book      Storage plus the projections read off it.
    policy    Every configurable number, in one place.
    engine    Replay: apply a day's events, then close the day.
    report    Text rendering of the replay.
    scenario  The brief's six-day event stream, as data.
"""

__all__ = ["book", "engine", "money", "policy", "records", "report", "scenario"]
