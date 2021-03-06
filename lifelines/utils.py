# -*- coding: utf-8 -*-
from __future__ import print_function, division

from datetime import datetime

import numpy as np
import pandas as pd
from pandas import to_datetime


def coalesce(*args):
    return next(s for s in args if s is not None)


def group_survival_table_from_events(groups, durations, event_observed, min_observations, limit=-1):
    """
    Joins multiple event series together into dataframes. A generalization of
    `survival_table_from_events` to data with groups. Previously called `group_event_series` pre 0.2.3.

    Parameters:
        groups: a (n,) array of individuals' group ids.
        durations: a (n,)  array of durations of each individual
        event_observed: a (n,) array of event observations, 1 if observed, 0 else.
        event_observed: a (n,) array of times individual entered study. This is most applicable in
                    cases where there is left-truncation, i.e. a individual might enter the
                    study late. If not the case, normally set to all zeros.

    Output:
        - np.array of unique groups
        - dataframe of removal count data at event_times for each group, column names are 'removed:<group name>'
        - dataframe of observed count data at event_times for each group, column names are 'observed:<group name>'
        - dataframe of censored count data at event_times for each group, column names are 'censored:<group name>'

    Example:
        #input
        group_survival_table_from_events(waltonG, waltonT, np.ones_like(waltonT)) #data available in test_suite.py

        #output
        [
            array(['control', 'miR-137'], dtype=object),

                      removed:control  removed:miR-137
            event_at
            6                       0                1
            7                       2                0
            9                       0                3
            13                      0                3
            15                      0                2
            ,
                      observed:control  observed:miR-137
            event_at
            6                        0                 1
            7                        2                 0
            9                        0                 3
            13                       0                 3
            15                       0                 2
            ,
                      censored:control  censored:miR-137
            event_at
            6                        0                 0
            7                        0                 0
            9                        0                 0
            ,
        ]

    """
    n = max(groups.shape)
    assert n == max(durations.shape) == max(event_observed.shape) == max(min_observations.shape), "inputs must be of the same length."
    groups, durations, event_observed, min_observations = map(lambda x: pd.Series(np.reshape(x, (n,))), [groups, durations, event_observed, min_observations])
    unique_groups = groups.unique()

    # set first group
    g = unique_groups[0]
    ix = (groups == g)
    T = durations[ix]
    C = event_observed[ix]
    B = min_observations[ix]

    g_name = str(g)
    data = survival_table_from_events(T, C, B,
                                      columns=['removed:' + g_name, "observed:" + g_name, 'censored:' + g_name, 'entrance' + g_name])
    for g in unique_groups[1:]:
        ix = groups == g
        T = durations[ix]
        C = event_observed[ix]
        B = min_observations[ix]
        g_name = str(g)
        data = data.join(survival_table_from_events(T, C, B,
                                                    columns=['removed:' + g_name, "observed:" + g_name, 'censored:' + g_name, 'entrance' + g_name]),
                         how='outer')
    data = data.fillna(0)
    # hmmm pandas its too bad I can't do data.ix[:limit] and leave out the if.
    if int(limit) != -1:
        data = data.ix[:limit]
    return unique_groups, data.filter(like='removed:'), data.filter(like='observed:'), data.filter(like='censored:')


def survival_table_from_events(durations, event_observed, min_observations,
                               columns=["removed", "observed", "censored", 'entrance'], weights=None):
    """
    Parameters:
        durations: (n,1) array of event times (durations individual was observed for)
        event_observed: (n,1) boolean array, 1 if observed event, 0 is censored event.
        min_observations: used for left truncation data. Sometimes subjects will show
          up late in the study. min_observations is a (n,1) array of positive numbers representing
          when the subject was first observed. A subject's life is then [min observation + duration observed]
        columns: a 3-length array to call the, in order, removed individuals, observed deaths
          and censorships.

    Returns:
        Pandas DataFrame with index as the unique times in event_times. The columns named
        'removed' refers to the number of individuals who were removed from the population
        by the end of the period. The column 'observed' refers to the number of removed
        individuals who were observed to have died (i.e. not censored.) The column
        'censored' is defined as 'removed' - 'observed' (the number of individuals who
         left the population due to event_observed)

    Example:
        #input
        survival_table_from_events( waltonT, np.ones_like(waltonT)) #available in test suite

        #output

                  removed  observed  censored
        event_at
        6               1         1         0
        7               2         2         0
        9               3         3         0
        13              3         3         0
        15              2         2         0

    """
    # deal with deaths and censorships

    durations = np.asarray(durations) + min_observations
    df = pd.DataFrame(durations, columns=["event_at"])
    df[columns[0]] = 1 if weights is None else weights
    df[columns[1]] = event_observed
    death_table = df.groupby("event_at").sum()
    death_table[columns[2]] = (death_table[columns[0]] - death_table[columns[1]]).astype(int)

    # deal with late births
    births = pd.DataFrame(min_observations, columns=['event_at'])
    births[columns[3]] = 1
    births_table = births.groupby('event_at').sum()

    # this next line can be optimized for when min_observerations is all zeros.
    event_table = death_table.join(births_table, how='outer', sort=True).fillna(0)  # http://wesmckinney.com/blog/?p=414

    return event_table


def survival_events_from_table(event_table, observed_deaths_col="observed", censored_col="censored"):
    """
    This is the inverse of the function ``survival_table_from_events``.

    Parameters
        event_table: a pandas DataFrame with index as the durations (!!) and columns "observed" and "censored", referring to
           the number of individuals that died and were censored at time t.

    Returns
        T: a np.array of durations of observation -- one element for each individual in the population.
        C: a np.array of event observations -- one element for each individual in the population. 1 if observed, 0 else.

    Ex: The survival table, as a pandas DataFrame:

                      observed  censored
        index
        1                1         0
        2                0         1
        3                1         0
        4                1         1
        5                0         1

    would return
        T = np.array([ 1.,  2.,  3.,  4.,  4.,  5.]),
        C = np.array([ 1.,  0.,  1.,  1.,  0.,  0.])

    """
    columns = [observed_deaths_col, censored_col]
    N = event_table[columns].sum().sum()
    T = np.empty(N)
    C = np.empty(N)
    i = 0
    for event_time, row in event_table.iterrows():
        n = row[columns].sum()
        T[i:i + n] = event_time
        C[i:i + n] = np.r_[np.ones(row[columns[0]]), np.zeros(row[columns[1]])]
        i += n

    return T, C


def datetimes_to_durations(start_times, end_times, fill_date=datetime.today(), freq='D', dayfirst=False, na_values=None):
    """
    This is a very flexible function for transforming arrays of start_times and end_times
    to the proper format for lifelines: duration and event observation arrays.

    Parameters:
        start_times: an array, series or dataframe of start times. These can be strings, or datetimes.
        end_times: an array, series or dataframe of end times. These can be strings, or datetimes.
                   These values can be None, or an empty string, which corresponds to censorship.
        fill_date: the date to use if end_times is a None or empty string. This corresponds to last date
                  of observation. Anything above this date is also censored. Default: datetime.today()
        freq: the units of time to use.  See pandas 'freq'. Default 'D' for days.
        day_first: convert assuming European-style dates, i.e. day/month/year.
        na_values : Additional string to recognize as NA/NaN. Ex: ['']

    Returns:
        T: a array of floats representing the durations with time units given by freq.
        C: a boolean array of event observations: 1 if death observed, 0 else.

    """
    freq_string = 'timedelta64[%s]' % freq
    start_times = pd.Series(start_times).copy()
    end_times = pd.Series(end_times).copy()
    start_times_ = to_datetime(start_times, dayfirst=dayfirst)

    C = ~(pd.isnull(end_times).values | (end_times == "") | (end_times == na_values))
    end_times[~C] = fill_date
    """
    c =  (to_datetime(end_times, dayfirst=dayfirst, coerce=True) > fill_date)
    end_times[c] = fill_date
    C += c
    """
    end_times_ = to_datetime(end_times, dayfirst=dayfirst, coerce=True)

    T = (end_times_ - start_times_).map(lambda x: x.astype(freq_string).astype(float))
    if (T < 0).sum():
        print("Warning: some values of start_times are before end_times")
    return T.values, C.values


class StatError(Exception):

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return repr(self.msg)


def inv_normal_cdf(p):
    if p < 0.5:
        return -AandS_approximation(p)
    else:
        return AandS_approximation(1 - p)


def AandS_approximation(p):
    # Formula 26.2.23 from A&S and help from John Cook ;)
    # http://www.johndcook.com/normal_cdf_inverse.html
    c_0 = 2.515517
    c_1 = 0.802853
    c_2 = 0.010328

    d_1 = 1.432788
    d_2 = 0.189269
    d_3 = 0.001308

    t = np.sqrt(-2 * np.log(p))

    return t - (c_0 + c_1 * t + c_2 * t ** 2) / (1 + d_1 * t + d_2 * t * t + d_3 * t ** 3)


def k_fold_cross_validation(fitter, df, duration_col='T', event_col='E',
                            k=5, loss_function="concordance", predictor="predict_median",
                            predictor_kwargs={}):
    """
    Perform cross validation on a dataset.

    fitter: either an instance of AalenAdditiveFitter or CoxPHFitter.
    df: a Pandas dataframe with necessary columns `duration_col` and `event_col`, plus
        other covariates. `duration_col` refers to the lifetimes of the subjects. `event_col`
        refers to whether the 'death' events was observed: 1 if observed, 0 else (censored).
    duration_col: the column in dataframe that contains the subjects lifetimes.
    event_col: the column in dataframe that contains the subject's death observation.    loss functions:
    k: the number of folds to perform. n/k data will be withheld for testing on.
    loss_function: "concordance" only.
            "concordance":  concordance index (C-index) between two series of event times
    predictor: a string that matches a prediction method on the fitter instances. For example,
            "predict_expectation" or "predict_percentile". Default is "predict_median"
    predictor_kwargs: keyward args to pass into predictor.

    Returns:
        (k,1) array of scores for each fold.
    """
    from .statistics import concordance_index

    n, d = df.shape
    scores = np.zeros((k,))
    df = df.copy()
    df = df.reindex(np.random.permutation(df.index)).sort(event_col)

    assignments = np.array((n // k + 1) * list(range(1, k + 1)))
    assignments = assignments[:n]

    testing_columns = df.columns - [duration_col, event_col]

    for i in range(1, k + 1):

        ix = assignments == i
        training_data = df.ix[~ix]
        testing_data = df.ix[ix]

        T_actual = testing_data[duration_col].values
        E_actual = testing_data[event_col].values
        X_testing = testing_data[testing_columns]

        # fit the fitter to the training data
        fitter.fit(training_data, duration_col=duration_col, event_col=event_col)
        T_pred = getattr(fitter, predictor)(X_testing, **predictor_kwargs).values

        scores[i - 1] = concordance_index(T_actual, T_pred, E_actual)

    return scores


def epanechnikov_kernel(t, T, bandwidth=1.):
    M = 0.75 * (1 - (t - T) / bandwidth) ** 2
    M[abs((t - T)) >= bandwidth] = 0
    return M
