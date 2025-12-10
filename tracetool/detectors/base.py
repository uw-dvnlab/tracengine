import pandas as pd
from tracetool.data.descriptors import Signal

class Detector:
    name = "base"

    def required_signals(self) -> list[str]:
        return []

    def run(self, signals: dict[str, Signal]) -> pd.DataFrame:
        """
        Returns dataframe with events: columns ['time', 'type', ...]
        """
        raise NotImplementedError
