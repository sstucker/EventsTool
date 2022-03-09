"""
Module for wrappers on BIDS-specified text files and structures
"""

import csv
import json
import os
import warnings

import numpy as np
from pysnirf2 import Snirf

try:
    import tabulate
except ModuleNotFoundError:  # Weird dependency issue
    pass


SNIRF_STIM_ONSET_DESCRIPTION = 'Time relative to the time origin when the stimulus takes on a value.'
SNIRF_STIM_ONSET_UNITS = 's'
SNIRF_STIM_DURATION_DESCRIPTION = 'The time in seconds that the stimulus value continues following the onset.'
SNIRF_STIM_DURATION_UNITS = 's'
SNIRF_STIM_AMPLITUDE_DESCRIPTION = 'Amplitude of the stimulus (from SNIRF).'
SNIRF_STIM_NAME_DESCRIPTION = 'A string describing the stimulus condition (from SNIRF).'

class DictWrapper:
    """
    Class which provides a dictionary via 'data' property.
    """

    def __init__(self):
        self._dict = {}

    @property
    def data(self):
        return self._dict
    
    @data.setter
    def data(self, value):
        if type(value) is dict:
            self._dict = value
        else:
            raise ValueError("'data' must be type dict")
    
    def __setitem__(self, item, value):
        self._dict[item] = value
        
    def __getitem__(self, item):
        return self._dict[item]
    
    def keys(self):
        return self._dict.keys()

    def values(self):
        return self._dict.values()


class EventColumn(DictWrapper):
    """A column of an events.tsv file as specified by BIDS, corresponding to all `Event` instances with the column `name`.

    `data` is a nested dict of the sidecar descriptions of the column, key-able by the field.
    """

    def __init__(self, name: str, data: dict = {}):
        super().__init__()
        self.name = name
        self.data = data


class Event(DictWrapper):
    """A row of an events.tsv file as specified by BIDS.

    `data` is a dict of the values key-able by their column name.
    """

    def __init__(self, data: dict):
        super().__init__()
        self.data = data

    def __repr__(self):
        try:
            return super().__repr__() + '\n' + tabulate.tabulate(self.values(), headers=self.keys())
        except Exception:
            return super().__repr__()


class Events:
    """Interface and model for BIDS event data.

    Example:
        ```
        events = Events('*_events.tsv')
        print(events)
        ```
    """

    def __init__(self, filename: str = None, sidecar: str = None):

        self._columns: list[EventColumn] = []
        self._rows: list[Event] = []

        # Assigned by load
        self._filename = None
        self._sidecar = None
        self.task = None

        if filename is not None:
            self.load(filename, sidecar)

    def __repr__(self):
        try:
            return super().__repr__() + '\n' \
               + tabulate.tabulate(self.data, headers=self.column_names) \
               + '\n' + json.dumps(self.column_descriptions, indent=4, sort_keys=True)
        except Exception:
            return super().__repr__()
    
    def save(self, filename: str, sidecar: str = None):
        """Save the event data to disk in BIDS tabular format with an optional JSON `sidecar`."""

        with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.column_names, delimiter="\t", quotechar='"')
            writer.writeheader()
            for row in self._rows:
                writer.writerow(row.data)
        if sidecar is not None:
            with open(sidecar, 'w') as f:
                json.dump(self.column_descriptions, f, indent=4)
    
    def load(self, filename: str, sidecar: str = None):
        """Load the event data from a text or SNIRF file (and, optionally, a .json sidecar) on disk.

        Args:
            filename (str): Path to `*_events.tsv` file or `_nirs.snirf` file.
            sidecar (optional str): Path to `*_events.json` sidecar file. If set to `"search"`, will traverse BIDS dataset
                                    for an `*_events.json` file with the same `_task-` label.
        """

        self._columns = []
        self._rows = []
        self._filename = filename
        self._sidecar = sidecar

        # Extract task name from tsv or SNIRF name if provided
        self.task = filename.partition("task-")[2].partition("_")[0]

        if sidecar == 'search':  # Search above the tsv file for an inherited sidecar file with the same task name
            if self.task == '':
                raise ValueError('Cannot search for the sidecar file corresponding to {}. No _task-<label> found.'.format(filename))
            current_dir = os.path.dirname(filename)
            sidecar_contents = None
            for lvl in range(4):  # Modality, Session, Subject, Dataset
                # print('Searching', current_dir)
                files = os.listdir(current_dir)
                for file in files:
                    if file.endswith('_events.json') and self.task in file:
                        with open(os.path.join(current_dir, file)) as f:
                            sidecar_contents = json.load(f)
                        break
                current_dir = os.path.dirname(current_dir)
        elif sidecar is not None:
            with open(sidecar) as f:
                sidecar_contents = json.load(f)
        else:
            sidecar_contents = None

        if filename.endswith('_events.tsv'):
            self._load_tsv(filename, sidecar_contents)
        elif filename.endswith('.snirf'):
            self._load_snirf(filename, sidecar_contents)
        else:
            raise ValueError('Cannot load {}, not .SNIRF or _events.tsv.'.format(filename))
        # self.sort_events()

    def _load_tsv(self, tsv: str, sidecar_contents: dict):
        with open(tsv, encoding='utf-8-sig') as f:  # TODO make sure this encoding is generalizable
            reader = csv.DictReader(f, delimiter="\t", quotechar='"')
            # Get columns from the csv file
            for key in reader.fieldnames:
                if key not in self.column_names:  # TODO remove this if redundant. Maybe DictReader rejects duplicates
                    col = EventColumn(key)
                    # Include sidecar fields if they exist
                    if sidecar_contents is not None:
                        if key in sidecar_contents.keys():
                            col.data = sidecar_contents[key]
                    self._columns.append(col)
            for row in reader:
                self._rows.append(Event(dict(row)))

    def _load_snirf(self, snirf: str, sidecar_contents: dict):
        print('Loading', snirf)
        with Snirf(snirf) as s:
            for nirs in s.nirs:
                for stim in nirs.stim:
                    ncol = stim.data.shape[1]
                    if stim.dataLabels is not None:  # TODO test
                        column_names = stim.dataLabels
                    else:
                        column_names= ['onset', 'duration', 'value']
                    column_names = column_names[0:ncol]  # Truncate labels to columns of stim. This permits invalid stim data arrays to be converted
                    if len(column_names) < ncol:  # Add default names to unlabeled additional columns
                        column_names += ["column{}".format(i) for i in range(ncol - len(column_names))]
                    column_names += ['trial_type']
                    for key in column_names:
                        if key not in self.column_names:
                            col = EventColumn(key)
                            # Give columns some defualt sidecar descriptions
                            if key == 'onset':
                                col.data = {'Description': SNIRF_STIM_ONSET_DESCRIPTION, 'Units': SNIRF_STIM_ONSET_UNITS}
                            elif key == 'duration':
                                col.data = {'Description': SNIRF_STIM_DURATION_DESCRIPTION, 'Units': SNIRF_STIM_DURATION_UNITS}
                            elif key == 'value':
                                col.data = {'Description': SNIRF_STIM_AMPLITUDE_DESCRIPTION}
                            elif key == 'trial_type':    
                                col.data = {'trial_type': SNIRF_STIM_NAME_DESCRIPTION}
                            # Overwrite with sidecar fields if they exist
                            if sidecar_contents is not None:
                                if key in sidecar_contents.keys():
                                    col.data = sidecar_contents[key]
                            self._columns.append(col)
                    for i in range(stim.data.shape[0]):
                        event_data = {}
                        for j in range(stim.data.shape[1]):
                            event_data[column_names[j]] = stim.data[i, j]
                        event_data['trial_type'] = stim.name
                        self._rows.append(Event(event_data))

    @property
    def data(self) -> list:
        return [row.values() for row in self._rows]

    @property
    def column_names(self) -> list:
        return [col.name for col in self._columns]

    @property
    def column_descriptions(self) -> dict:
        s = {}
        for col in self._columns:
            s[col.name] = col.data
        return s
    
    def sort_events(self):
        """Reorder the events by their onset."""
        try:
            onsets = self.get_column('onset')
        except KeyError(self):
            warnings.warn("Events '{}' not sorted. No 'onset' column.")
        new_rows = []
        for i in np.argsort(onsets).astype(int):
            new_rows.append(self._rows[i])
        self._rows = new_rows
        
    def get_column(self, name) -> list:
        """Returns the column with `name` as a list."""
        return [row[name] for row in self._rows]

def snirf_to_bids(snirf: str, output: str, sidecar: str=None):
    """Converts SNIRF file at `snirf` to BIDS `*_event.tsv` with optional `*_events.json` sidecar."""
    events = Events(snirf)
    events.save(output, sidecar=sidecar)


if __name__ == '__main__':

    bids_events = Events('test/bids-examples/eeg_ds003654s_hed/sub-003/eeg/sub-003_task-FacePerception_run-2_events.tsv', sidecar='search')
    print(bids_events)

    snirf_to_bids('test/bids-examples/BIDS-NIRS-Tapping-master/sub-01/nirs/sub-01_task-tapping_nirs.snirf',
                  'test/output/sub-01_task-tapping_events.tsv', 'test/output/sub-01_task-tapping_events.json')
