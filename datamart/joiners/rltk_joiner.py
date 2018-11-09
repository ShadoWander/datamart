import pandas as pd
from datamart.joiners.joiner_base import JoinerBase

"""
TODO
Implement RLTK joiner
"""


class RLTKJoiner(JoinerBase):

    def __init__(self):
        pass

    def join(self, left_df, right_df, left_columns, right_columns) -> pd.DataFrame:
        return pd.merge(left=left_df,
                        right=right_df,
                        left_on=[left_df.columns[idx] for idx in left_columns],
                        right_on=[right_df.columns[idx] for idx in right_columns],
                        how='left')
