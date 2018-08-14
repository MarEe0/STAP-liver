"""This script computes the dice cost for an "optimal" solution built from the ground truth."""

"""Full Liver segmentation module for the SRG.

This module contains specific configurations
for the SRG, in order to make it segment livers.

Authors:
 * Mateus Riva (mriva@ime.usp.br)
"""

from liver_full_functions import *

initial_weights = (1,1,1,1)
vertex_weights = (1,1,1,1,10)
edge_weights = (1,1,1,1,1)
graph_weights = (1,1)

#if __name__ == '__main__':
# Step 1: Loading data
# -----------------------
model_patient = Patient.build_from_folder("data/4")
model_volume, model_labelmap = model_patient.volumes['t2'], model_patient.labelmaps['t2']
# Reconfiguring model_labelmap with extra backgrounds and unified liver
model_labelmap.data += 1 # Adding space for the automatic "body" label
model_labelmap.data[np.logical_and(model_volume.data < 10, model_labelmap.data == 1)] = 0 # automatic body
model_labelmap.data += 1 # Adding space for the split background
model_labelmap.data[:model_labelmap.data.shape[1]//2,:,:][model_labelmap.data[:model_labelmap.data.shape[1]//2,:,:] == 1] = 0 # splitting background
model_labelmap.data[model_labelmap.data == 3] = 2 # vena cava is body
model_labelmap.data[model_labelmap.data >= 4] = 3 # portal, hepatic veins are 'liver'
# getting center of body
body_center = [int(x) for x in measure_center_of_mass(np.ones_like(model_labelmap.data), labels=model_labelmap.data, index=range(4))[2]]
model_labelmap.data = model_labelmap.data + 7 # adding space for the body divisions
model_labelmap.data[model_labelmap.data == 7] = 0
model_labelmap.data[model_labelmap.data == 8] = 1
# Splitting the body into 8 cubes, based on centroid
model_labelmap.data[:body_center[0],:body_center[1],:body_center[2]][model_labelmap.data[:body_center[0],:body_center[1],:body_center[2]] == 9] = 2
model_labelmap.data[:body_center[0],:body_center[1],body_center[2]:][model_labelmap.data[:body_center[0],:body_center[1],body_center[2]:] == 9] = 3
model_labelmap.data[:body_center[0],body_center[1]:,:body_center[2]][model_labelmap.data[:body_center[0],body_center[1]:,:body_center[2]] == 9] = 4
model_labelmap.data[:body_center[0],body_center[1]:,body_center[2]:][model_labelmap.data[:body_center[0],body_center[1]:,body_center[2]:] == 9] = 5
model_labelmap.data[body_center[0]:,:body_center[1],:body_center[2]][model_labelmap.data[body_center[0]:,:body_center[1],:body_center[2]] == 9] = 6
model_labelmap.data[body_center[0]:,:body_center[1],body_center[2]:][model_labelmap.data[body_center[0]:,:body_center[1],body_center[2]:] == 9] = 7
model_labelmap.data[body_center[0]:,body_center[1]:,:body_center[2]][model_labelmap.data[body_center[0]:,body_center[1]:,:body_center[2]] == 9] = 8

#display_volume(model_labelmap.data, cmap=class_colors)
# display_overlayed_volume(model_volume.data, model_labelmap.data, label_colors=[(0,0,0),(0.1,0.1,0.1),(0.40,0.40,0.40),(0.42,0.42,0.42),(0.44,0.44,0.44),(0.46,0.46,0.46),(0.48,0.48,0.48),(0.50,0.50,0.50),(0.52,0.52,0.52),(0.54,0.54,0.54),(1,0,0),(0,1,0)], title="Model")

observation_volume = deepcopy(model_volume)

# Step 2: Generating model graph
# -----------------------
model_graph = build_graph(model_volume.data, model_labelmap.data)
model_graph, mean_vertex, std_vertex, mean_edge, std_edge = normalize_graph(model_graph)
print("Model:",represent_srg(model_graph, class_names=class_names))

# Step 3: Generating observation
# -----------------------
# Applying gradient
smoothed = ndi.gaussian_filter(observation_volume.data, (5,5,1))
smoothed = smoothed/np.max(smoothed) # normalization for magnitude
#display_volume(smoothed, cmap="gray")
magnitude = np.sqrt(ndi.filters.sobel(smoothed, axis=0)**2 + ndi.filters.sobel(smoothed, axis=1)**2 + ndi.filters.sobel(smoothed, axis=2)**2)
#display_volume(magnitude, cmap="gray", title="Magnitude")
observed_labelmap_data = watershed(magnitude, markers=500, compactness=0.001)-1
display_segments_as_lines(observation_volume.data, observed_labelmap_data)
#display_volume(observed_labelmap_data,cmap=ListedColormap(np.random.rand(255,3)))
#display_overlayed_volume(observation_volume.data, observed_labelmap_data, label_colors=np.random.rand(255,3),width=1,level=0.5)

# Step 4: Generating super-observation graph
# -----------------------
super_graph = build_graph(observation_volume.data, observed_labelmap_data, add_edges=False)
super_graph = normalize_graph(super_graph,mean_vertex, std_vertex, mean_edge, std_edge)
super_adjacency = rag.RAG(observed_labelmap_data)
# print("Superobservation:",represent_srg(super_graph))

# Step 5: Generating optimal solution
# -----------------------
solution = np.empty(super_graph.vertices.shape[0])
for i, super_vertex in enumerate(super_graph.vertices):
    # Computing cost to all model vertices
    labels, counts = np.unique(model_labelmap.data[np.where(observed_labelmap_data == i)], return_counts=True)
    solution[i] = labels[np.argmax(counts)]
# print("Initial solution:")
# for i, prediction in enumerate(solution):
#     print("\t{}: {}".format(i, prediction))


#print("End of epoch #{}: solution = {}".format(epoch,solution))
joined_labelmap_data = np.zeros_like(observed_labelmap_data)
for label, model_vertex in enumerate(model_graph.vertices):
    joined_labelmap_data[np.isin(observed_labelmap_data, np.where(solution==label))]=label
observation_graph = build_graph(observation_volume.data, joined_labelmap_data, target_vertices=model_graph.vertices.shape[0])
observation_graph = normalize_graph(observation_graph, mean_vertex, std_vertex, mean_edge, std_edge)
vertex_costs = compute_vertex_cost(observation_graph.vertices, model_graph.vertices, weights=vertex_weights)
edge_costs = compute_edge_cost(observation_graph.edges, model_graph.edges, weights=edge_weights)
dice = (2. * np.logical_and(joined_labelmap_data==10, model_labelmap.data == 10)).sum()/((joined_labelmap_data==10).sum() + (model_labelmap.data == 10).sum())
print("Optimal Solution (Costs: {:.3f},{:.3f}), Dice: {:.4f}".format(np.mean(vertex_costs),np.mean(edge_costs), dice))
print("Observation:",represent_srg(observation_graph, class_names=class_names))

display_volume(joined_labelmap_data, cmap=class_colors, title="Optimal Solution (Costs: {:.3f},{:.3f})".format(np.mean(vertex_costs),np.mean(edge_costs)))
