"""Operations to support categorical data."""

import logging
from collections import OrderedDict, namedtuple
from multiprocessing import Pool

import numpy as np
from typing import Tuple, List


from landshark.basetypes import CategoricalArraySource, CategoricalType
from landshark import iteration

log = logging.getLogger(__name__)

CategoryInfo = namedtuple("CategoryInfo", ["mappings", "counts", "missing"])


def _unique_values(x: np.ndarray) \
        -> Tuple[List[np.ndarray], List[int]]:
    """
    Return unique values and their counts from an array.

    The last dimension of the values is assumed to be features.

    """
    x = x.reshape((-1), x.shape[-1])
    unique_vals, counts = zip(*[np.unique(c, return_counts=True)
                                for c in x.T])
    return unique_vals, counts


class _CategoryAccumulator:
    """Class for accumulating categorical values and their counts."""

    def __init__(self) -> None:
        """Initialise the object."""
        self.counts: OrderedDict = OrderedDict()

    def update(self, values: np.ndarray, counts: np.ndarray) -> None:
        """Add a new set of values from a batch."""
        assert values.ndim == 1
        assert counts.ndim == 1
        assert values.shape == counts.shape
        assert counts.dtype == int
        assert np.all(counts >= 0)
        for v, c in zip(values, counts):
            if v in self.counts:
                self.counts[v] += c
            else:
                self.counts[v] = c


def get_categories(array_src: CategoricalArraySource,
                   batchsize: int,
                   pool: Pool) -> CategoryInfo:
    """
    Extract the unique categorical variables and their counts.

    Parameters
    ----------
    array_src : CategoricalArraySource
        The data source to examine.
    batchsize : int
        The number of rows to examine in one iteration (by 1 proc)
    pool : multiprocessing.Pool
        The pool of processes over which to distribute the work.

    Returns
    -------
    category_info : CategoryInfo
    mappings : List[np.ndarray]
        The mapping of unique values for each feature.
    counts : List[np.ndarray]
        The counts of unique values for each feature.
    missing : List[Optional[int]]

    """
    n_rows = array_src.shape[0]
    n_features = array_src.shape[-1]
    missing_values = array_src.missing
    accums = [_CategoryAccumulator() for _ in range(n_features)]

    # Add the missing values initially as zeros
    for acc, m in zip(accums, missing_values):
        if m is not None:
            acc.update(np.array([m]), np.array([0], dtype=int))

    it = iteration.batch_slices(batchsize, n_rows)
    data_it = ((array_src.slice(start, end)) for start, end in it)
    out_it = pool.imap(_unique_values, data_it)

    log.info("Computing unique values in categorical features:")
    for unique_vals, counts in out_it:
        for a, u, c in zip(accums, unique_vals, counts):
            a.update(u, c)

    missing = [CategoricalType(0) if k is not None else None
               for k in missing_values]
    count_dicts = [m.counts for m in accums]
    mappings = [np.array(list(c.keys())) for c in count_dicts]
    counts = [np.array(list(c.values()), dtype=np.int64) for c in count_dicts]
    result = CategoryInfo(mappings=mappings, counts=counts, missing=missing)
    return result


class CategoricalOutputTransform:
    """
    Callable object that maps n categorical values to 0..n-1.

    Parameters
    ----------
    mappings : List[np.ndarray]
        A list of ndarrays, one for each feature (corresponding to the
        final dimension of input). A value of v at position i in the ndarray
        implies a mapping from v to i.

    """

    def __init__(self, mappings: List[np.ndarray]) -> None:
        """Initialise the object with a set of mappings."""
        self.mappings = mappings

    def __call__(self, x: np.ndarray) -> np.ndarray:
        """
        Transform the values by the mapping given at initialisation.

        Parameters
        ----------
        x : np.ndarray
            The categorical to transform.

        Returns
        -------
        new_array : np.ndarray
            An array of the same shape as CategoricalValues.categorical
            but with the mapping applied so values are 0..n-1.

        """
        assert x.shape[-1] == len(self.mappings)
        new_array = np.zeros_like(x, dtype=CategoricalType)
        for col_idx, m in enumerate(self.mappings):
            old_col = x[..., col_idx]
            new_col = new_array[..., col_idx]
            for i, v in enumerate(m):
                indices = old_col == v
                new_col[indices] = i
        return new_array
