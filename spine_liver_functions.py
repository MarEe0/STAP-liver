import numpy as np
import math
from scipy.ndimage.measurements import center_of_mass as measure_center_of_mass
from time import time
from copy import deepcopy
from itertools import product
from skimage.morphology import watershed, h_minima, ball, local_minima
from skimage.color import rgb2gray, gray2rgb
import skimage.segmentation as skis
import scipy.ndimage as ndi
from matplotlib.colors import ListedColormap
from skimage.util import random_noise
from skimage.filters import try_all_threshold, threshold_otsu, rank
import skimage.future.graph as rag

from srg import SRG
from patient import Patient, LabelMap, Volume
from display_utils import display_volume, display_segments_as_lines, display_solution, represent_srg, display_overlayed_volume
#class_colors = ListedColormap([(0,0,0),(0.1,0.1,0.1),(0.40,0.40,0.40),(0.42,0.42,0.42),(0.44,0.44,0.44),(0.46,0.46,0.46),(0.48,0.48,0.48),(0.50,0.50,0.50),(0.52,0.52,0.52),(0.54,0.54,0.54),(1,0,0),(0,1,0)])
#class_names = ["BG Posterior","BG Anterior", "BG Body1  ", "BG Body2  ", "BG Body3  ", "BG Body4  ", "BG Body5  ", "BG Body6  ", "BG Body7  ", "BG Body8  ", "Vena Cava", "Full Liver"]
class_colors = ListedColormap([(0,0,0),(0.1,0.1,0.1),(0.40,0.40,0.40),(0.42,0.42,0.42),(0.44,0.44,0.44),(0.46,0.46,0.46),(0.48,0.48,0.48),(0.50,0.50,0.50),(0.52,0.52,0.52),(0.54,0.54,0.54),(0,1,0),(0,1,1),(0,1,1)])
class_names = ["BG Posterior","BG Anterior", "BG Body1  ", "BG Body2  ", "BG Body3  ", "BG Body4  ", "BG Body5  ", "BG Body6  ", "BG Body7  ", "BG Body8  ", "Full Liver", "Vertebrae", "Spinal Cord"]



def compute_attributes(volume, labelmap, attribute):
    """Computes an specific attribute for an entire volume"""
    if attribute == "centroid":
        labels = np.unique(labelmap)
        centroids = measure_center_of_mass(np.ones_like(labelmap), labels=labelmap, index=labels)
        centroids = np.array(centroids)
        return centroids
    elif attribute == "intensity":
        labels, indexes = np.unique(labelmap, return_inverse=True)
        intensities = np.empty(len(labels))
        for i, label in enumerate(labels):
            intensities[i] = np.mean(volume.flatten()[indexes==i])
        return intensities
    elif attribute == "size":
        labels,voxel_count_per_labels = np.unique(labelmap, return_counts=True)
        sizes = voxel_count_per_labels
        return sizes
    else:
        raise Exception("{} is not a supported attribute".format(attribute))

def build_graph(volume,labelmap,add_edges=True, target_vertices=None):
    """Builds a graph from an annotated volume."""
    # Compute statistical attributes
    centroids = compute_attributes(volume, labelmap, attribute="centroid")
    intensities = compute_attributes(volume, labelmap, attribute="intensity")
    sizes = compute_attributes(volume, labelmap, attribute="size")

    # Assemble statistical attributes as the vertex matrix
    if target_vertices is None:
        vertices = np.column_stack([centroids, intensities, sizes])
    else:
        vertices = np.empty((target_vertices, 5))
        actual_labels = np.unique(labelmap)
        actual_index = 0
        for i, label in enumerate(range(target_vertices)):
            if label in actual_labels:
                vertices[label] = np.append(centroids[actual_index],(intensities[actual_index],sizes[actual_index]))
                actual_index += 1
            else:
                vertices[label] = np.array([math.inf]*5)

    if not add_edges:
        return SRG(vertices, np.array([]), ["centroid_x", "centroid_y", "centroid_z", "intensity", "size"] ,[])
    else:
        # Compute relational attributes
        centroids = vertices[:,:3]
        intensities = vertices[:,3]
        sizes = vertices[:,4]
        positions = np.repeat(centroids, centroids.shape[0],axis=0) - np.vstack([centroids]*centroids.shape[0])
        contrasts = abs(np.repeat(intensities, intensities.shape[0],axis=0) - np.hstack([intensities]*intensities.shape[0]))
        ratios = np.repeat(sizes, sizes.shape[0],axis=0) / np.hstack([sizes]*sizes.shape[0])
        # Assemble relational attributes as the edges matrix
        edges = np.column_stack([positions, contrasts, ratios])

        # Initializing and returning the SRG
        return SRG(vertices, edges, ["centroid_x", "centroid_y", "centroid_z", "intensity", "size"], ["position_x","position_y","position_z","contrast","ratio"])#, "contrast", "ratio"])

def normalize_graph(graph, mean_vertex=None, std_vertex=None, mean_edge=None, std_edge=None):
    """Normalizes a graph's vertex and edge attributes to a given mean and std.

    If any mean and std are not specified, then they will be computed and returned."""
    return_values = False
    if mean_vertex is None or std_vertex is None or mean_edge is None or std_edge is None:
        return_values = True

    vertices = graph.vertices
    if mean_vertex is None: mean_vertex = vertices.mean(axis=0)
    if std_vertex is None: std_vertex = vertices.std(axis=0)
    std_vertex[std_vertex==0] = 1
    vertices = (vertices - mean_vertex) / std_vertex
    graph.vertices = vertices

    if len(graph.edges) > 0:
        edges = graph.edges
        if mean_edge is None: mean_edge = edges.mean(axis=0)
        if std_edge is None: std_edge = edges.std(axis=0)
        std_edge[std_edge==0] = 1
        edges = (edges - mean_edge) / std_edge
        graph.edges = edges

    if return_values:
        return graph, mean_vertex, std_vertex, mean_edge, std_edge
    else:
        return graph

def compute_initial_vertex_cost(vertices1, vertices2, weights=None):
    """Computes initial vertex cost (ignoring size)"""
    if weights is None:
        weights = np.ones(vertices1.shape[1]-1)
    weights = np.array(weights)/sum(weights)
    costs = np.linalg.norm(weights*(vertices1[:,:-1]-vertices2[:,:-1]), axis=-1)
    return costs


def compute_vertex_cost(vertices1, vertices2, weights=None):
    """Computes initial vertex cost (ignoring size)"""
    if weights is None:
        weights = np.ones(vertices1.shape[1])
    weights = np.array(weights)/sum(weights)
    costs = np.linalg.norm(weights*(vertices1-vertices2), axis=-1)
    return costs


def compute_edge_cost(edges1, edges2, weights=None):
    """Computes edge cost (using vector dissimilarity)"""
    if weights is None:
        weights = np.ones(edges1.shape[1])
    weights = np.array(weights)/sum(weights)
    costs = np.linalg.norm(weights*(edges1-edges2), axis=-1)
    return costs


def anisotropic_seeds(shape, amounts):
    """Like `skimage.util.regular_seeds` but anisotropic. Only works for 3D images."""
    assert len(shape)==3, "Only 3D is implemented"
    assert len(shape)==len(amounts)
    steps = [axis//amount for axis,amount in zip(shape,amounts)]
    seeds = np.zeros(shape)
    seeds[shape[0]//(2*amounts[0])::shape[0]//amounts[0],shape[1]//(2*amounts[1])::shape[1]//amounts[1],shape[2]//(2*amounts[2])::shape[2]//amounts[2]]=1
    return seeds

def dice_coefficient(dist1, dist2):
    """Computes Dice's coefficient (similarity index) between two samples"""
    return (2. * np.logical_and(dist1, dist2)).sum()/((dist1).sum() + (dist2).sum())
