import pymesh
import numpy as np

def electrode_position_sphere(radius, theta, phi=0):
	"""[summary]

	Args:
		radius ([type]): [description]
		theta ([type]): [description]
		phi (int, optional): [description]. Defaults to 0.

	Returns:
		[type]: [description]
	"""
	return np.array([radius*np.cos(np.deg2rad(phi))*np.cos(np.deg2rad(theta)), radius*np.cos(np.deg2rad(phi))*np.sin(np.deg2rad(theta)), radius*np.sin(np.deg2rad(phi))])

def orient_electrode_sphere(mesh, init_point, delta_point):
	"""[summary]

	Args:
		mesh ([type]): [description]
		init_point ([type]): [description]
		delta_point ([type]): [description]

	Returns:
		[type]: [description]
	"""
	dist = pymesh.signed_distance_to_mesh(mesh, init_point)
	face = dist[1][0]
	#
	# Create a vector with the direction of the face
	p_1 = mesh.vertices[mesh.faces[face][0]]
	p_2 = mesh.vertices[mesh.faces[face][1]]
	dir_vector = p_1 - p_2
	dir_vector = dir_vector/np.linalg.norm(dir_vector)
	
	normal = np.cross(delta_point, dir_vector)
	return normal/np.linalg.norm(normal)

def orient_electrode(mesh, init_point):
	"""Orient the electrode along the surface. Connectivy shall be enabled in the mesh that has been given.

	Args:
		mesh ([type]): [description]
		init_point ([type]): [description:

	Returns:
		[type]: [description]
	"""
	point_id = np.where(np.sum(mesh.vertices == init_point, axis=1))[0][0] # Unique point assumed
	face = mesh.get_vertex_adjacent_faces(point_id)[0]

	points = []
	for point in mesh.vertices[mesh.faces[face]]:
		if np.sum(point != init_point):
			points.append(point)
	p_1 = points[0] - init_point
	p_2 = points[1] - init_point

	normal = np.cross(p_1, p_2)
	return normal/np.linalg.norm(normal)

def add_electrode(surface_mesh, electrode_mesh):
	"""[summary]

	Args:
		surface_mesh ([type]): [description]
		electrode_mesh ([type]): [description]

	Returns:
		[type]: [description]
	"""
	# Get the surface outline including the electrode
	model = pymesh.merge_meshes((surface_mesh, electrode_mesh))
	outer_hull = pymesh.compute_outer_hull(model)
	
	# Create the surface with the electrode mesh imprinted
	electrode_tan_mesh = pymesh.boolean(electrode_mesh, surface_mesh, 'difference')
	outer_diff = pymesh.boolean(outer_hull, electrode_tan_mesh, 'difference')
	conditioned_surface = pymesh.merge_meshes((outer_diff, electrode_tan_mesh))

	# Generate the surface with the electrode on
	face_id = np.arange(conditioned_surface.num_faces)
	conditioned_surface = pymesh.remove_duplicated_vertices(conditioned_surface)[0] # Remove any duplicate vertices
	
	return [pymesh.submesh(conditioned_surface, np.isin(face_id, pymesh.detect_self_intersection(conditioned_surface)[:, 0], invert=True), 0), outer_diff]  # Get rid of the duplicate faces on the tangent surface, without merging the points

def electrode_separate(mesh, bounding_roi):
	"""Separate the electrodes from the surface of the head

	Args:
		mesh (pymesh.Mesh.Mesh): Complete mesh of the object to separate the electrodes
		bounding_roi (dict): Dictionary containing the bounds in X, Y, Z plane for the box of the electrode

	Returns:
		list: The first element contains the submesh with the ROI data and the second contains the rest mesh elements
	"""
	# Bounding ROI
	vert_x = np.logical_and(mesh.vertices[:, 0] >= bounding_roi['x_min'], mesh.vertices[:, 0] <= bounding_roi['x_max'])
	vert_y = np.logical_and(mesh.vertices[:, 1] >= bounding_roi['y_min'], mesh.vertices[:, 1] <= bounding_roi['y_max'])
	vert_z = np.logical_and(mesh.vertices[:, 2] >= bounding_roi['z_min'], mesh.vertices[:, 2] <= bounding_roi['z_max'])
	
	# Get the ROI vertex indices
	vert_id_roi = np.arange(mesh.num_vertices)
	roi_ids = (vert_x * vert_y * vert_z > 0)

	# Calculate the resulting voxels ROI
	vox_id_roi = np.isin(mesh.voxels, vert_id_roi[roi_ids])
	vox_id_roi = np.where(vox_id_roi == True)[0]
	vox_id_roi = np.unique(vox_id_roi)

	# Calculate the rest voxels
	vox_id_rest = np.isin(mesh.voxels, vert_id_roi[roi_ids], invert=True)
	vox_id_rest = np.where(vox_id_rest == True)[0]
	vox_id_rest = np.unique(vox_id_rest)

	if vox_id_rest.size == 0:
		return [pymesh.submesh(mesh, vox_id_roi, 0), 0]
	else:
		return [pymesh.submesh(mesh, vox_id_roi, 0), pymesh.submesh(mesh, vox_id_rest, 0)]

def electrodes_separate(model, domains: list, bounds: list):
	"""Separate an array of electrodes into individual meshes

	Args:
		model (pymesh.Mesh.Mesh): The complete meshed model
		domains (list): The first element shall have the surface mesh and the second the electrode array mesh
		bounds (list): Bounds of each individual electrode

	Returns:
		list: First element contains a list of the individual electrodes and the second element contains the surface with any missing points
	"""
	electrodes = [] # Create an empty list of electrodes
	electrode = electrode_separate(domains[1], bounds[0]) # First element
	electrodes.append(electrode[0])

	del bounds[0] # Remove the first element from the list

	for bound in bounds:
		electrode = electrode_separate(electrode[1], bound)
		electrodes.append(electrode[0])
	
	if type(electrode[1]) is int:
		rest_surface = pymesh.submesh(model, np.hstack((domains[0].get_attribute('ori_voxel_index').astype(np.int32))), 0)
	else:
		rest_surface = pymesh.submesh(model, np.hstack((domains[0].get_attribute('ori_voxel_index').astype(np.int32), electrode[1].get_attribute('ori_voxel_index').astype(np.int32))), 0)


	return [electrodes, rest_surface]

def standard_electrode_positioning(elec_names, elec_coords, surface_mesh, width = 3, radius = 4, elements = 150):
	electrode_array = {}
	closest_point = pymesh.distance_to_mesh(surface_mesh, elec_coords)[1] # Get the closest point to the one provided

	i = 0
	for electrode_name in elec_names:
		p_i = surface_mesh.vertices[surface_mesh.faces[closest_point[i]]][0] # Get the surface vertex coordinates
		elec_orient = orient_electrode(surface_mesh, p_i) # Orient the electrode perpendicular to the surface

		# Generate the electrode cylinder and save to the output dictionary
		elec_cylinder = pymesh.generate_cylinder(p_i - (width * elec_orient)/4., p_i + (width * elec_orient)/4., radius, radius, elements)
		electrode_array[electrode_name] = {
			'mesh': elec_cylinder,
			'dom_roi': {
				'x_min': np.amin(elec_cylinder.vertices[:, 0]),
				'x_max': np.amax(elec_cylinder.vertices[:, 0]),
				'y_min': np.amin(elec_cylinder.vertices[:, 1]),
				'y_max': np.amax(elec_cylinder.vertices[:, 1]),
				'z_min': np.amin(elec_cylinder.vertices[:, 2]),
				'z_max': np.amax(elec_cylinder.vertices[:, 2]),
				},
			}
		i = i + 1

	return electrode_array