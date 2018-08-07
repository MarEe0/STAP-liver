"""Functions for calibrating the pipeline with dummies.
This module contains both functions for generating dummies,
and for putting them through the segmentation pipeline."""

from calibration_functions import *

#if __name__ == '__main__':
# Step 1: Loading data (generating dummies)
# -----------------------
#model_dummy, model_labelmap = generate_dummy(3), generate_dummy_label(3)
#model_dummy, model_labelmap = generate_checkerboard_dummy((4,4,2), (30,30,30), np.arange(4*4*2)*50)
#model_dummy, model_labelmap = generate_moons_dummy(20,20,3,1,0.5)
model_dummy, model_labelmap = generate_liver_phantom_dummy()
# Splitting the model: body into 8, bg into 2
body_center = [int(x) for x in measure_center_of_mass(np.ones_like(model_labelmap), labels=model_labelmap, index=range(4))[1]]
model_labelmap = model_labelmap + 8
model_labelmap[model_labelmap.shape[1]//2:,:,:][model_labelmap[model_labelmap.shape[1]//2:,:,:] == 8] = 1
model_labelmap[model_labelmap == 8] = 0
# Splitting the body into 8 cubes, based on centroid
model_labelmap[:body_center[0],:body_center[1],:body_center[2]][model_labelmap[:body_center[0],:body_center[1],:body_center[2]] == 9] = 2
model_labelmap[:body_center[0],:body_center[1],body_center[2]:][model_labelmap[:body_center[0],:body_center[1],body_center[2]:] == 9] = 3
model_labelmap[:body_center[0],body_center[1]:,:body_center[2]][model_labelmap[:body_center[0],body_center[1]:,:body_center[2]] == 9] = 4
model_labelmap[:body_center[0],body_center[1]:,body_center[2]:][model_labelmap[:body_center[0],body_center[1]:,body_center[2]:] == 9] = 5
model_labelmap[body_center[0]:,:body_center[1],:body_center[2]][model_labelmap[body_center[0]:,:body_center[1],:body_center[2]] == 9] = 6
model_labelmap[body_center[0]:,:body_center[1],body_center[2]:][model_labelmap[body_center[0]:,:body_center[1],body_center[2]:] == 9] = 7
model_labelmap[body_center[0]:,body_center[1]:,:body_center[2]][model_labelmap[body_center[0]:,body_center[1]:,:body_center[2]] == 9] = 8
#model_labelmap[body_center[0]:,body_center[1]:,body_center[2]:][model_labelmap[body_center[0]:,body_center[1]:,body_center[2]:] == 9] = 9
#display_volume(model_dummy, cmap="gray", title="Model Input")
# display_volume(model_labelmap, cmap=color_map, title="Model Input")
#observation_dummy = generate_dummy(2)
#observation_dummy = np.random.normal(model_dummy, 20)
#observation_dummy = deepcopy(model_dummy)
observation_dummy = generate_fat_salt_and_pepper_noise(model_dummy, radius=7,amount=0.000015, seed=0)
observation_dummy[np.logical_or(model_labelmap == 0, model_labelmap == 1)] = 0
#observation_dummy = random_noise(model_dummy, "speckle", seed=10) #amount=0.05)
# display_volume(observation_dummy, cmap="gray", title="Observation Input")

# Step 2: Generating model graph
# -----------------------
model_graph = build_graph(model_dummy, model_labelmap)
model_graph, mean_vertex, std_vertex, mean_edge, std_edge = normalize_graph(model_graph)
print("Model:",represent_srg(model_graph, class_names=class_names))
# Step 3: Generating observation
# -----------------------
# Applying gradient
smoothed = ndi.gaussian_filter(observation_dummy, (5,5,1))
#display_volume(smoothed, cmap="gray")
magnitude = np.sqrt(ndi.filters.sobel(smoothed, axis=0)**2 + ndi.filters.sobel(smoothed, axis=1)**2 + ndi.filters.sobel(smoothed, axis=2)**2)
#display_volume(magnitude, cmap="gray", title="Magnitude")
# Getting local minima of the volume with a structural element 5x5x1
#volume_local_minima = local_minima(magnitude)
# volume_local_minima = h_minima(magnitude, h=0.1)
#display_volume(volume_local_minima)
# Labeling local_minima
# markers, total_markers = ndi.label(volume_local_minima)
# observed_labelmap = watershed(magnitude,markers=markers)-1
observed_labelmap = watershed(magnitude, markers=500, compactness=0.001)-1
# observed_labelmap = skis.slic(observation_dummy, n_segments=500,
                    # compactness=0.0001, multichannel=False, sigma=(5,5,1))
display_segments_as_lines(observation_dummy, observed_labelmap, width=1, level=0.5)
# display_volume(observed_labelmap,cmap=ListedColormap(np.random.rand(255,3)))
#display_overlayed_volume(observation_dummy, observed_labelmap, label_colors=np.random.rand(255,3),width=1,level=0.5)

# Step 4: Generating super-observation graph
# -----------------------
super_graph = build_graph(observation_dummy, observed_labelmap, add_edges=False)
super_graph = normalize_graph(super_graph,mean_vertex, std_vertex, mean_edge, std_edge)
super_adjacency = rag.RAG(observed_labelmap)
#print("Superobservation:",represent_srg(super_graph))

# Step 5: Generating initial solution
# -----------------------
solution = np.empty(super_graph.vertices.shape[0])
solution_costs = np.empty_like(solution)
for i, super_vertex in enumerate(super_graph.vertices):
    # Computing cost to all model vertices
    super_vertex_matrix = np.vstack([super_vertex]*model_graph.vertices.shape[0])
    costs = compute_initial_vertex_cost(super_vertex_matrix, model_graph.vertices, weights=(1,1,1,7))
    solution[i] = np.argmin(costs)
    solution_costs[i] = np.min(costs)
# print("Initial solution:")
# for i, prediction in enumerate(solution):
#     print("\t{}: {}".format(i, prediction))

#solution = np.array([0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0.,       0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0.,       0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0.,       1., 1., 1., 1., 1., 0., 1., 1., 1., 1., 0., 1., 1., 1., 1., 1., 1.,       1., 1., 1., 1., 0., 1., 1., 1., 1., 1., 1., 0., 0., 1., 1., 1., 0.,       1., 1., 1., 0., 0., 0., 4., 1., 1., 1., 0., 0., 0., 1., 1., 4., 1.,       0., 1., 0., 3., 1., 1., 3., 4., 4., 3., 1., 1., 0., 1., 1., 1., 3.,       1., 1., 4., 4., 0., 3., 1., 4., 2., 4., 2., 1., 4., 4., 1., 1., 1.,       1., 1., 4., 1., 1., 1., 1., 1., 1., 4., 1., 1., 1., 1., 1., 1., 1.,       1., 1., 4., 1., 1., 4., 1., 1., 4., 4., 4., 4., 1., 4., 4., 4., 1.,       4., 0., 1., 1., 1., 4., 4., 4., 4., 1., 4., 4., 4., 4., 4., 4., 4.,       4., 1., 1., 4., 4., 4., 4., 1., 4., 4., 4., 4., 4., 4., 4., 4., 4.,       4., 4., 4., 4., 4., 4., 4., 4., 4., 4., 4., 4., 4., 4., 4., 4., 4.,       4., 4., 4., 4., 4., 4., 4., 4., 4., 4.])

# Step 6: Region Joining
# -----------------------
vertex_weights = (1,1,1,7,1)
edge_weights = (1,1,1,1,1)
graph_weights = (1,1)
joined_labelmap = np.zeros_like(observed_labelmap)
for element, prediction in enumerate(solution):
    joined_labelmap[observed_labelmap==element]=prediction
observation_graph = build_graph(observation_dummy, joined_labelmap, target_vertices=model_graph.vertices.shape[0])
observation_graph = normalize_graph(observation_graph, mean_vertex, std_vertex, mean_edge, std_edge)
vertex_costs = compute_vertex_cost(observation_graph.vertices, model_graph.vertices, weights=vertex_weights)
edge_costs = compute_edge_cost(observation_graph.edges, model_graph.edges, weights=edge_weights)
print("Joined Initial Solution (Costs: {:.3f},{:.3f})".format(np.mean(vertex_costs),np.mean(edge_costs)))
display_volume(joined_labelmap, cmap=color_map, title="Joined Initial Solution (Costs: {:.3f},{:.3f})".format(np.mean(vertex_costs),np.mean(edge_costs)))
print("Observation:",represent_srg(observation_graph, class_names=class_names))

# Step 7: Improvement
# -----------------------
total_epochs = 200#len(solution)
improvement_cutoff = 1#len(solution) # TODO: convergence? cutoff by cost difference?
for epoch in range(total_epochs):
    # attempting to improve each vertex, starting from the most expensive
    for super_vertex_index, _ in sorted(enumerate(solution_costs), key=lambda x: x[1], reverse=True)[:improvement_cutoff]:
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
            working_labelmap = deepcopy(joined_labelmap)
            working_labelmap[observed_labelmap==super_vertex_index] = potential_prediction_index

            # Updating graph
            working_graph = build_graph(observation_dummy, working_labelmap, target_vertices=model_graph.vertices.shape[0])
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

        if current_prediction_index == solution[super_vertex_index]:
            print("\t* No replacement, still {}".format(current_prediction_index))
        else:
            print("\t* Replaced with {}".format(current_prediction_index))

        solution[super_vertex_index] = current_prediction_index
        solution_costs[super_vertex_index] = 0#np.mean(current_vertex_costs)

    # End of an epoch, rebuilding the joined graph
    print("End of epoch #{}".format(epoch))
    #print("End of epoch #{}: solution = {}".format(epoch,solution))
    joined_labelmap = np.zeros_like(observed_labelmap)
    for element, prediction in enumerate(solution):
        joined_labelmap[observed_labelmap==element]=prediction
    observation_graph = build_graph(observation_dummy, joined_labelmap, target_vertices=model_graph.vertices.shape[0])
    observation_graph = normalize_graph(observation_graph, mean_vertex, std_vertex, mean_edge, std_edge)
    vertex_costs = compute_vertex_cost(observation_graph.vertices, model_graph.vertices, weights=vertex_weights)
    edge_costs = compute_edge_cost(observation_graph.edges, model_graph.edges, weights=edge_weights)
    print("Epoch {} Solution (Costs: {:.3f},{:.3f})".format(epoch,np.mean(vertex_costs),np.mean(edge_costs)))
    #display_volume(joined_labelmap, cmap=color_map, title="Epoch {} Solution (Costs: {:.3f},{:.3f})".format(epoch, np.mean(vertex_costs),np.mean(edge_costs)))
    print("Observation:",represent_srg(observation_graph, class_names=class_names))

display_volume(joined_labelmap, cmap=color_map, title="Epoch {} Solution (Costs: {:.3f},{:.3f})".format(epoch, np.mean(vertex_costs),np.mean(edge_costs)))

# TODO: histogramas dos atributos
