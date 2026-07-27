"""DCA-signal study: does 0050's black-K improve dollar-cost-averaging into 2330?

Not a low-point predictor and not an optimiser — it asks whether, with a fixed
monthly budget and no knowledge of the future, using market pullbacks (0050
down days) as entry timing beats plain dollar-cost averaging into TSMC, after
accounting for cash drag.
"""

from . import data, signals, engine  # noqa: F401

__version__ = "0.1.0"
