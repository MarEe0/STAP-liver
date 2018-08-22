"""This script segments a full liver from few slices, using 2D supersegmentations.

Authors:
 * Mateus Riva (mriva@ime.usp.br)
"""
import os,sys,inspect
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0,parentdir)
from liver_full_functions import *

class_colors = ListedColormap([(0,0,0),(0.1,0.1,0.1),(0.40,0.40,0.40),(0.42,0.42,0.42),(0.44,0.44,0.44),(0.46,0.46,0.46),(0,1,0)])
class_names = ["BG Posterior","BG Anterior", "BG Body1  ", "BG Body2  ", "BG Body3  ", "BG Body4  ", "Full Liver"]

initial_weights = (1,1,0,1)
vertex_weights = (1,1,0,1,10)
edge_weights = (1,1,0,1,1)
graph_weights = (1,1)

#if __name__ == '__main__':
# Step 1: Loading data
# -----------------------
model_patient = Patient.build_from_folder("data/4")
model_volume, model_labelmap = model_patient.volumes['t2'], model_patient.labelmaps['t2']
model_volume.data = model_volume.data[...,26:34]
model_labelmap.data = model_labelmap.data[...,26:34]
# Reconfiguring model_labelmap with extra backgrounds and unified liver
model_labelmap.data += 1 # Adding space for the automatic "body" label
model_labelmap.data[np.logical_and(model_volume.data < 10, model_labelmap.data == 1)] = 0 # automatic body
model_labelmap.data += 1 # Adding space for the split background
model_labelmap.data[:model_labelmap.data.shape[1]//2,:,:][model_labelmap.data[:model_labelmap.data.shape[1]//2,:,:] == 1] = 0 # splitting background
model_labelmap.data[model_labelmap.data == 3] = 2 # vena cava is body
model_labelmap.data[model_labelmap.data >= 4] = 3 # portal, hepatic veins are 'liver'
# getting center of body
body_center = [int(x) for x in measure_center_of_mass(np.ones_like(model_labelmap.data), labels=model_labelmap.data, index=range(4))[2]]
model_labelmap.data = model_labelmap.data + 3 # adding space for the body divisions
model_labelmap.data[model_labelmap.data == 3] = 0
model_labelmap.data[model_labelmap.data == 4] = 1
# Splitting the body into 8 cubes, based on centroid
model_labelmap.data[:body_center[0],:body_center[1],:][model_labelmap.data[:body_center[0],:body_center[1],:] == 5] = 2
model_labelmap.data[:body_center[0],body_center[1]:,:][model_labelmap.data[:body_center[0],body_center[1]:,:] == 5] = 3
model_labelmap.data[body_center[0]:,:body_center[1],:][model_labelmap.data[body_center[0]:,:body_center[1],:] == 5] = 4
model_labelmap.data[body_center[0]:,body_center[1]:,:][model_labelmap.data[body_center[0]:,body_center[1]:,:] == 5] = 5

# display_volume(model_labelmap.data, cmap=class_colors)
#display_overlayed_volume(model_volume.data, model_labelmap.data, label_colors=[(0,0,0),(0.1,0.1,0.1),(0.40,0.40,0.40),(0.42,0.42,0.42),(0.44,0.44,0.44),(0.46,0.46,0.46),(0.48,0.48,0.48),(0.50,0.50,0.50),(0.52,0.52,0.52),(0.54,0.54,0.54),(1,0,0),(0,1,0)], title="Model")

observation_volume = deepcopy(model_volume)

# Step 2: Generating model graph
# -----------------------
model_graph = build_graph(model_volume.data, model_labelmap.data)
model_graph, mean_vertex, std_vertex, mean_edge, std_edge = normalize_graph(model_graph)
print("Model:",represent_srg(model_graph, class_names=class_names))

# Step 3: Generating observation
# -----------------------
observed_labelmap_data = np.zeros_like(observation_volume.data)
current_start_region = 0
# Iterating over slice
i = 0
for i in range(observation_volume.data.shape[2]):
    slice = observation_volume.data[:,:,i]
    # Applying gradient
    smoothed = ndi.gaussian_filter(slice, (3,3))
    smoothed = smoothed/np.max(smoothed) # normalization for magnitude
    #display_volume(smoothed, cmap="gray")
    magnitude = np.sqrt(ndi.filters.sobel(smoothed, axis=0)**2 + ndi.filters.sobel(smoothed, axis=1)**2)
    #display_volume(magnitude, cmap="gray", title="Magnitude")
    observed_labelmap_data[:,:,i] = watershed(magnitude, markers=400, compactness=0.001)-1 + current_start_region
    current_start_region = np.max(observed_labelmap_data)+1
# display_segments_as_lines(observation_volume.data, observed_labelmap_data)
# display_volume(observed_labelmap_data,cmap=ListedColormap(np.random.rand(800,3)))
#display_overlayed_volume(observation_volume.data, observed_labelmap_data, label_colors=np.random.rand(255,3),width=1,level=0.5)

# Step 4: Generating super-observation graph
# -----------------------
super_graph = build_graph(observation_volume.data, observed_labelmap_data, add_edges=False)
super_graph = normalize_graph(super_graph,mean_vertex, std_vertex, mean_edge, std_edge)
super_adjacency = rag.RAG(observed_labelmap_data)
# print("Superobservation:",represent_srg(super_graph))

# Step 5: Generating initial solution
# -----------------------
solution = np.empty(super_graph.vertices.shape[0])
solution_costs = np.empty_like(solution)
for i, super_vertex in enumerate(super_graph.vertices):
    # Computing cost to all model vertices
    super_vertex_matrix = np.vstack([super_vertex]*model_graph.vertices.shape[0])
    costs = compute_initial_vertex_cost(super_vertex_matrix, model_graph.vertices, weights=initial_weights)
    solution[i] = np.argmin(costs)
    solution_costs[i] = np.min(costs)
# print("Initial solution:")
# for i, prediction in enumerate(solution):
#     print("\t{}: {}".format(i, prediction))

# Step 6: Contiguity guarantee
# -----------------------
# Detecting non-contiguous regions
for label, model_vertex in enumerate(model_graph.vertices):
    # label = 0
    # model_vertex = model_graph.vertices[0]
    # Get all contiguous regions for this label
    label_regions = np.where(solution==label)
    solution_map = np.isin(observed_labelmap_data , label_regions)
    # Label connected components
    potential_region_map, potential_region_count = ndi.label(solution_map)
    if potential_region_count == 1: # No need to change contiguous predictions
        continue

    # Computing vertex attributes for each connected component
    potential_region_super_graph = build_graph(observation_volume.data, potential_region_map, add_edges=False)
    potential_region_super_graph = normalize_graph(potential_region_super_graph,mean_vertex, std_vertex, mean_edge, std_edge)
    # Computing costs
    model_label_vertex_matrix = np.vstack([model_vertex]*potential_region_super_graph.vertices.shape[0])
    costs = compute_initial_vertex_cost(potential_region_super_graph.vertices, model_label_vertex_matrix, weights=initial_weights)
    actual_region = (np.argmin(costs[1:])) + 1 # Actual region is the one with the lowest cost; however, do note it can never be region zero
    # Determining which supervertexes compose the actual region
    correct_vertexes = np.unique(observed_labelmap_data[potential_region_map==actual_region])
    # Marking other regions for improvement
    solution[label_regions] = -1
    solution[correct_vertexes] = label

# Running improvement for non-contiguous regions
while -1 in solution:
    joined_labelmap_data = np.zeros_like(observed_labelmap_data)
    for label, model_vertex in enumerate(model_graph.vertices):
        joined_labelmap_data[np.isin(observed_labelmap_data, np.where(solution==label))]=label
    for super_vertex_index, super_vertex in sorted(enumerate(solution_costs), key=lambda x: x[1], reverse=True):
        if solution[super_vertex_index] > -1:
            continue # Ignore continuous regions, for now

        potential_predictions = set([solution[neighbour] for neighbour in super_adjacency.adj[super_vertex_index].keys()])

        current_cost = float("inf")
        current_prediction_index = solution[super_vertex_index]
        print("Modifying supervertex {} (curr: {}, cost: {:.6f})".format(super_vertex_index, current_prediction_index, current_cost))

        # Soft contiguity: potential predictions may only be neighboring labels
        for potential_prediction_index in potential_predictions:
            # Skipping same replacements
            if potential_prediction_index == current_prediction_index: continue
            if potential_prediction_index == -1: continue

            # Replacing the current prediction with the potential
            working_labelmap_data = deepcopy(joined_labelmap_data)
            working_labelmap_data[observed_labelmap_data==super_vertex_index] = potential_prediction_index

            # Updating graph
            working_graph = build_graph(observation_volume.data, working_labelmap_data, target_vertices=model_graph.vertices.shape[0])
            working_graph = normalize_graph(working_graph, mean_vertex, std_vertex, mean_edge, std_edge)

            # Computing costs
            potential_vertex_costs = compute_vertex_cost(working_graph.vertices, model_graph.vertices, weights=vertex_weights)
            potential_edge_costs = compute_edge_cost(working_graph.edges, model_graph.edges)
            potential_cost = graph_weights[0]*np.mean(potential_vertex_costs) + graph_weights[1]*np.mean(potential_edge_costs)
            print("\tAttempting replace with {}, cost: {:.6f}".format(potential_prediction_index, potential_cost))
            # Improving if better
            if potential_cost < current_cost:
                current_prediction_index = potential_prediction_index
                current_vertex_costs = potential_vertex_costs
                current_edge_costs = potential_edge_costs
                current_cost = potential_cost

        print("\t* Replaced with {}".format(current_prediction_index))

        solution[super_vertex_index] = current_prediction_index

# End of an epoch, rebuilding the joined graph
print("End of contiguity guarantee")
#print("End of epoch #{}: solution = {}".format(epoch,solution))
joined_labelmap_data = np.zeros_like(observed_labelmap_data)
for label, model_vertex in enumerate(model_graph.vertices):
    joined_labelmap_data[np.isin(observed_labelmap_data, np.where(solution==label))]=label
observation_graph = build_graph(observation_volume.data, joined_labelmap_data, target_vertices=model_graph.vertices.shape[0])
observation_graph = normalize_graph(observation_graph, mean_vertex, std_vertex, mean_edge, std_edge)
vertex_costs = compute_vertex_cost(observation_graph.vertices, model_graph.vertices, weights=vertex_weights)
edge_costs = compute_edge_cost(observation_graph.edges, model_graph.edges, weights=edge_weights)
dice = (2. * np.logical_and(joined_labelmap_data==6, model_labelmap.data==6)).sum()/((joined_labelmap_data==6).sum() + (model_labelmap.data==6).sum())
print("Contiguous Solution (Costs: {:.3f},{:.3f}), Dice: {:.4f}".format(np.mean(vertex_costs),np.mean(edge_costs), dice))
print("Observation:",represent_srg(observation_graph, class_names=class_names))

display_volume(joined_labelmap_data, cmap=class_colors, title="Contiguous Solution (Costs: {:.3f},{:.3f})".format(np.mean(vertex_costs),np.mean(edge_costs)))


# Step 6: Region Joining
# -----------------------
joined_labelmap_data = np.zeros_like(observed_labelmap_data)
for element, prediction in enumerate(solution):
    joined_labelmap_data[observed_labelmap_data==element]=prediction
observation_graph = build_graph(observation_volume.data, joined_labelmap_data, target_vertices=model_graph.vertices.shape[0])
observation_graph = normalize_graph(observation_graph, mean_vertex, std_vertex, mean_edge, std_edge)
vertex_costs = compute_vertex_cost(observation_graph.vertices, model_graph.vertices, weights=vertex_weights)
edge_costs = compute_edge_cost(observation_graph.edges, model_graph.edges, weights=edge_weights)
dice = (2. * np.logical_and(joined_labelmap_data==6, model_labelmap.data==6)).sum()/((joined_labelmap_data==6).sum() + (model_labelmap.data==6).sum())
print("Joined Initial Solution (Costs: {:.3f},{:.3f}), Dice: {:.4f}".format(np.mean(vertex_costs),np.mean(edge_costs), dice))
display_volume(joined_labelmap_data, cmap=class_colors, title="Joined Initial Solution (Costs: {:.3f},{:.3f})".format(np.mean(vertex_costs),np.mean(edge_costs)))
print("Observation:",represent_srg(observation_graph, class_names=class_names))

# Displaying 3d point cloud for real and predicted liver
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
fig = plt.figure()
ax = fig.add_subplot(111, projection='3d')
# plotting prediction
ax.scatter(np.where(joined_labelmap_data==6)[0][::400], np.where(joined_labelmap_data==6)[1][::400],np.where(joined_labelmap_data==6)[2][::400], c="green")
ax.scatter(np.where(model_labelmap.data==6)[0][::400], np.where(model_labelmap.data==6)[1][::400],np.where(model_labelmap.data==6)[2][::400], c="red")
plt.show()

# Step 7: Improvement
# -----------------------
total_epochs = len(solution)//2
improvement_cutoff = 1#len(solution) # TODO: convergence? cutoff by cost difference?
for epoch in range(total_epochs):
    # attempting to improve each vertex, starting from the most expensive
    #for super_vertex_index, _ in sorted(enumerate(solution_costs), key=lambda x: x[1], reverse=True)[:improvement_cutoff]:
    for super_vertex_index in [np.argmax(solution_costs)]:
        current_prediction_index = solution[super_vertex_index]
        current_vertex_costs = compute_vertex_cost(observation_graph.vertices, model_graph.vertices, weights=vertex_weights)
        current_edge_costs = compute_edge_cost(observation_graph.edges, model_graph.edges, weights=edge_weights)
        current_cost = graph_weights[0]*np.mean(current_vertex_costs) + graph_weights[1]*np.mean(current_edge_costs)

        print("Modifying supervertex {} (curr: {}, cost: {:.6f})".format(super_vertex_index, current_prediction_index, current_cost))

        # Soft contiguity: potential predictions may only be neighboring labels
        potential_predictions = set([solution[neighbour] for neighbour in super_adjacency.adj[super_vertex_index].keys()])
        for potential_prediction_index in potential_predictions:
            # Skipping same replacements
            if potential_prediction_index == current_prediction_index: continue

            # Replacing the current prediction with the potential
            working_labelmap_data = deepcopy(joined_labelmap_data)
            working_labelmap_data[observed_labelmap_data==super_vertex_index] = potential_prediction_index

            # Updating graph
            working_graph = build_graph(observation_volume.data, working_labelmap_data, target_vertices=model_graph.vertices.shape[0])
            working_graph = normalize_graph(working_graph, mean_vertex, std_vertex, mean_edge, std_edge)

            # Computing costs
            potential_vertex_costs = compute_vertex_cost(working_graph.vertices, model_graph.vertices, weights=vertex_weights)
            potential_edge_costs = compute_edge_cost(working_graph.edges, model_graph.edges)
            potential_cost = graph_weights[0]*np.mean(potential_vertex_costs) + graph_weights[1]*np.mean(potential_edge_costs)
            print("\tAttempting replace with {}, cost: {:.6f}".format(potential_prediction_index, potential_cost))
            # Improving if better
            if potential_cost < current_cost:
                current_prediction_index = potential_prediction_index
                current_vertex_costs = potential_vertex_costs
                current_edge_costs = potential_edge_costs
                current_cost = potential_cost

        solution[super_vertex_index] = current_prediction_index
        solution_costs[super_vertex_index] = 0#np.mean(current_vertex_costs)

        print("\t* Replaced with {}".format(current_prediction_index))

    # End of an epoch, rebuilding the joined graph
    print("End of epoch #{}".format(epoch))
    #print("End of epoch #{}: solution = {}".format(epoch,solution))
    joined_labelmap_data = np.zeros_like(observed_labelmap_data)
    for element, prediction in enumerate(solution):
        joined_labelmap_data[observed_labelmap_data==element]=prediction
    observation_graph = build_graph(observation_volume.data, joined_labelmap_data, target_vertices=model_graph.vertices.shape[0])
    observation_graph = normalize_graph(observation_graph, mean_vertex, std_vertex, mean_edge, std_edge)
    vertex_costs = compute_vertex_cost(observation_graph.vertices, model_graph.vertices, weights=vertex_weights)
    edge_costs = compute_edge_cost(observation_graph.edges, model_graph.edges, weights=edge_weights)
    dice = (2. * np.logical_and(joined_labelmap_data==6, model_labelmap.data==6)).sum()/((joined_labelmap_data==6).sum() + (model_labelmap.data==6).sum())
    print("Epoch {} Solution (Costs: {:.3f},{:.3f}), Dice: {:.4f}".format(epoch, np.mean(vertex_costs),np.mean(edge_costs), dice))
    #display_volume(joined_labelmap_data, cmap=class_colors, title="Epoch {} Solution (Costs: {:.3f},{:.3f})".format(epoch, np.mean(vertex_costs),np.mean(edge_costs)))
    print("Observation:",represent_srg(observation_graph, class_names=class_names))

dice = (2. * np.logical_and(joined_labelmap_data==6, model_labelmap.data==6)).sum()/((joined_labelmap_data==6).sum() + (model_labelmap.data==6).sum())
print("Epoch {} Solution (Costs: {:.3f},{:.3f}), Dice: {:.4f}".format(epoch, np.mean(vertex_costs),np.mean(edge_costs), dice))
display_volume(joined_labelmap_data, cmap=class_colors, title="Epoch {} Solution (Costs: {:.3f},{:.3f})".format(epoch, np.mean(vertex_costs),np.mean(edge_costs)))

# TODO: histogramas dos atributos