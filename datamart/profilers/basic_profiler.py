import pandas as pd
import dateutil.parser
import typing
from datamart.metadata.variable_metadata import VariableMetadata
from datamart.metadata.global_metadata import GlobalMetadata


class BasicProfiler(object):
    def __init__(self):
        pass

    @staticmethod
    def profile_named_entity(column: pd.Series) -> typing.List[str]:
        """Profiling this named entities column, use when this column is marked as a named entities column.

        Args:
            column: pandas Series column.

        Returns:
            list of named entities string
        """

        return column.unique().tolist()

    @staticmethod
    def named_entity_recognize(column: pd.Series) -> typing.Union[typing.List[str], bool]:
        """Ideally run a NER on the column and profile.

        Args:
            column: pandas Series column.

        Returns:
            list of unique named entities strings in this column if contains named entity
            False if not a named entity column
        """

        "TODO"
        return False

    @staticmethod
    def profile_temporal_coverage(column: pd.Series, coverage: dict = None) -> typing.Union[dict, bool]:
        """Profiling this temporal column .

        Args:
            coverage: temporal coverage dict
            column: pandas Series column.

        Returns:
            temporal coverage dict
            False if there is no temporal related element detected
        """

        temporal_count = 0
        min_datetime = None
        max_datetime = None
        if len(column) == 0:
            return {
                "start": None,
                "end": None
            }

        for element in column:
            try:
                if isinstance(element, str):
                    this_datetime = dateutil.parser.parse(element)
                else:
                    if len(str(element)) == 4:
                        this_datetime = dateutil.parser.parse(str(element))
                    else:
                        break
                temporal_count += 1
                if not min_datetime:
                    min_datetime = this_datetime
                min_datetime = min(min_datetime, this_datetime)
                if not max_datetime:
                    max_datetime = this_datetime
                max_datetime = max(max_datetime, this_datetime)
            except:
                pass

        if not min_datetime and not max_datetime:
            return False

        if temporal_count < len(column) // 2:
            return False

        if not coverage:
            coverage = {
                "start": None,
                "end": None
            }

        if not coverage['start']:
            coverage['start'] = min_datetime.isoformat()
        if not coverage['end']:
            coverage['end'] = max_datetime.isoformat()
        return coverage

    @staticmethod
    def construct_variable_description(column: pd.Series) -> str:
        """construct description for this variable .

        Args:
            column: pandas Series column.

        Returns:
            string of description
        """

        ret = "column name: {}, dtype: {}".format(
            column.name, column.dtype
        )
        return ret

    @staticmethod
    def construct_global_title(data: pd.DataFrame) -> str:
        """construct title for this dataset .

        Args:
            data: pandas dataframe.

        Returns:
            string of title
        """

        return " ".join(data.columns.tolist())

    @staticmethod
    def construct_global_description(data: pd.DataFrame) -> str:
        """construct description for this dataset .

        Args:
            data: pandas dataframe.

        Returns:
            string of description
        """

        return ", ".join(["{} : {}".format(data.columns[i], data.dtypes[i]) for i in range(data.shape[1])])

    @staticmethod
    def construct_global_keywords(data: pd.DataFrame) -> str:
        """construct keywords for this dataset .

        Args:
            data: pandas dataframe.

        Returns:
            list of keywords
        """

        return data.columns.tolist()

    @classmethod
    def basic_profiling_column(cls,
                               description: dict,
                               variable_metadata: VariableMetadata,
                               column: pd.Series
                               ) -> VariableMetadata:
        """Profiling single column for necessary fields of metadata, if data is present .

        Args:
            description: description dict about the column.
            variable_metadata: the original VariableMetadata instance.
            column: the column to profile.

        Returns:
            profiled VariableMetadata instance
        """

        if not variable_metadata.name:
            variable_metadata.name = column.name

        if not variable_metadata.description:
            variable_metadata.description = cls.construct_variable_description(column)

        if variable_metadata.named_entity is None:
            variable_metadata.named_entity = cls.profile_named_entity(column)

        elif variable_metadata.named_entity is False and not description:
            named_entities = cls.named_entity_recognize(column)
            if named_entities:
                variable_metadata.named_entity = named_entities

        if variable_metadata.temporal_coverage is not False:
            if not variable_metadata.temporal_coverage['start'] or not variable_metadata.temporal_coverage['end']:
                variable_metadata.temporal_coverage = cls.profile_temporal_coverage(
                    column=column, coverage=variable_metadata.temporal_coverage)

        elif not description:
            temporal_coverage = cls.profile_temporal_coverage(column=column)
            if temporal_coverage:
                variable_metadata.temporal_coverage = temporal_coverage

        return variable_metadata

    @classmethod
    def basic_profiling_entire(cls, global_metadata: GlobalMetadata, data: pd.DataFrame) -> GlobalMetadata:
        """Profiling entire dataset for necessary fields of metadata, if data is present .

        Args:
            global_metadata: the original GlobalMetadata instance.
            data: dataframe of data.

        Returns:
            profiled GlobalMetadata instance
        """

        if not global_metadata.title:
            global_metadata.title = cls.construct_global_title(data)

        if not global_metadata.description:
            global_metadata.description = cls.construct_global_description(data)

        if not global_metadata.keywords:
            global_metadata.keywords = cls.construct_global_keywords(data)

        return global_metadata
