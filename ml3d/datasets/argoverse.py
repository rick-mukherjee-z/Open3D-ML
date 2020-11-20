import numpy as np
import os, argparse, pickle, sys
from os.path import exists, join, isfile, dirname, abspath, split
from pathlib import Path
from glob import glob
import logging
import yaml
import pyntcloud

from .base_dataset import BaseDataset
from ..utils import Config, make_dir, DATASET
from ..vis.boundingbox import BoundingBox3D

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(asctime)s - %(module)s - %(message)s',
)
log = logging.getLogger(__name__)


class Argoverse(BaseDataset):
    """
    Argoverse 3D dataset for Object Detection, used in visualizer, training, or test
    """

    def __init__(self,
                 dataset_path,
                 info_path,
                 name='Argoverse',
                 cache_dir='./logs/cache',
                 use_cache=False,
                 **kwargs):
        """
        Initialize
        Args:
            dataset_path (str): path to the dataset
            kwargs:
        """
        super().__init__(dataset_path=dataset_path,
                         info_path=info_path,
                         name=name,
                         cache_dir=cache_dir,
                         use_cache=use_cache,
                         **kwargs)

        cfg = self.cfg

        self.name = cfg.name
        self.dataset_path = cfg.dataset_path
        self.num_classes = 15
        self.label_to_names = self.get_label_to_names()

        self.train_info = {}
        self.test_info = {}
        self.val_info = {}

        if os.path.exists(join(info_path, 'infos_train.pkl')):
            self.train_info = pickle.load(
                open(join(info_path, 'infos_train.pkl'), 'rb'))

        if os.path.exists(join(info_path, 'infos_val.pkl')):
            self.val_info = pickle.load(
                open(join(info_path, 'infos_val.pkl'), 'rb'))

        if os.path.exists(join(info_path, 'infos_test.pkl')):
            self.test_info = pickle.load(
                open(join(info_path, 'infos_test.pkl'), 'rb'))

    @staticmethod
    def get_label_to_names():
        label_to_names = {
            0: 'ignore',
            1: 'VEHICLE',
            2: 'PEDESTRIAN',
            3: 'ON_ROAD_OBSTACLE',
            4: 'LARGE_VEHICLE',
            5: 'BICYCLE',
            6: 'BICYCLIST',
            7: 'BUS',
            8: 'OTHER_MOVER',
            9: 'TRAILER',
            10: 'MOTORCYCLIST',
            11: 'MOPED',
            12: 'MOTORCYCLE',
            13: 'STROLLER',
            14: 'EMERGENCY_VEHICLE',
            15: 'ANIMAL'
        }
        return label_to_names

    @staticmethod
    def read_lidar(path):
        assert Path(path).exists()

        data = pyntcloud.PyntCloud.from_file(path)
        x = np.array(data.points.x)[:, np.newaxis]
        y = np.array(data.points.y)[:, np.newaxis]
        z = np.array(data.points.z)[:, np.newaxis]

        return np.concatenate((x, y, z), axis=1)

    @staticmethod
    def read_label(bboxes):

        objects = []
        for box in bboxes:
            name = box['label_class']
            center = box['center']
            size = [box['w'], box['h'], box['l']]

            box2d = box['2d_coord']

            ry = np.arctan(
                (box2d[0][0] - box2d[1][0]) / (box2d[0][1] - box2d[1][1]))

            front = [np.cos(ry), np.sin(ry), 0]
            up = [0, 0, 1]
            left = [np.sin(ry), np.cos(ry), 0]

            objects.append(Object3d(center, front, up, left, size, name, box))

        return objects

    def get_split(self, split):
        return ArgoverseSplit(self, split=split)

    def get_split_list(self, split):
        if split in ['train', 'training']:
            return self.train_info
        elif split in ['test', 'testing']:
            return self.test_info
        elif split in ['val', 'validation']:
            return self.val_info

        raise ValueError("Invalid split {}".format(split))

    def is_tested():
        pass

    def save_test_result():
        pass


class ArgoverseSplit():

    def __init__(self, dataset, split='train'):
        self.cfg = dataset.cfg

        infos = dataset.get_split_list(split)

        self.num_pc = 0
        self.path_list = []
        self.bboxes = []

        for info in infos:
            self.num_pc += info['num_pc']
            self.path_list += info['lidar_path']
            self.bboxes += info['bbox']

        log.info("Found {} pointclouds for {}".format(self.num_pc, split))

        self.split = split
        self.dataset = dataset

    def __len__(self):
        return self.num_pc

    def get_data(self, idx):
        lidar_path = self.path_list[idx]
        bboxes = self.bboxes[idx]

        pc = self.dataset.read_lidar(lidar_path)

        label = self.dataset.read_label(bboxes)

        data = {
            'point': pc,
            'feat': None,
            'calib': None,
            'bounding_boxes': label,
        }

        return data

    def get_attr(self, idx):
        pc_path = self.path_list[idx]
        name = Path(pc_path).name.split('.')[0]

        attr = {'name': name, 'path': str(pc_path), 'split': self.split}
        return attr


class Object3d(BoundingBox3D):
    """
    Stores object specific details like bbox coordinates.
    """

    def __init__(self, center, front, up, left, size, name, box):
        label_class = self.cls_type_to_id(name)

        super().__init__(center, front, up, left, size, label_class, 1.0)

        self.name = name
        self.cls_id = self.cls_type_to_id(name)
        self.dis_to_cam = np.linalg.norm(self.center)
        self.occlusion = box['occlusion']
        self.quaternion = box['quaternion']
        self.coords_3d = box['3d_coord']
        self.coords_2d = box['2d_coord']

    @staticmethod
    def cls_type_to_id(cls_type):
        """
        get object id from name.
        """
        type_to_id = {
            'ignore': 0,
            'VEHICLE': 1,
            'PEDESTRIAN': 2,
            'ON_ROAD_OBSTACLE': 3,
            'LARGE_VEHICLE': 4,
            'BICYCLE': 5,
            'BICYCLIST': 6,
            'BUS': 7,
            'OTHER_MOVER': 8,
            'TRAILER': 9,
            'MOTORCYCLIST': 10,
            'MOPED': 11,
            'MOTORCYCLE': 12,
            'STROLLER': 13,
            'EMERGENCY_VEHICLE': 14,
            'ANIMAL': 15
        }
        if cls_type not in type_to_id.keys():
            return 0
        return type_to_id[cls_type]

    def generate_corners3d(self):
        """
        generate corners3d representation for this object
        :return corners_3d: (8, 3) corners of box3d in camera coord
        """
        return self.coords_3d


DATASET._register_module(Argoverse)
