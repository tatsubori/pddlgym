from pddlgym.parser import PDDLDomainParser, PDDLProblemParser
from pddlgym.structs import LiteralConjunction
from pddlgym.planning import run_ff
import pddlgym
import os
import numpy as np
from itertools import count
np.random.seed(0)


PDDLDIR = os.path.join(os.path.dirname(pddlgym.__file__), "pddl")
DOMAIN_NAME = "searchandrescue"


def get_random_location(locations_in_grid, rng=np.random):
    r = rng.randint(locations_in_grid.shape[0])
    c = rng.randint(locations_in_grid.shape[1])
    return locations_in_grid[r, c]

def sample_state(domain, num_rows=10, num_cols=10,
                 num_people=1,
                 randomize_person_loc=False,
                 randomize_robot_start=True,
                 wall_probability=0.05,
                 randomize_walls=False,
                 randomize_hospital_loc=False):

    person_type = domain.types['person']
    robot_type = domain.types['robot']
    location_type = domain.types['location']
    wall_type = domain.types['wall']
    hospital_type = domain.types['hospital']
    conn = domain.predicates['conn']
    clear = domain.predicates['clear']
    robot_at = domain.predicates['robot-at']
    person_at = domain.predicates['person-at']
    wall_at = domain.predicates['wall-at']
    hospital_at = domain.predicates['hospital-at']
    handsfree = domain.predicates['handsfree']
    move = domain.predicates['move']
    pickup = domain.predicates['pickup']
    dropoff = domain.predicates['dropoff']

    objects = set()
    state = set()
    locations_in_grid = np.empty((num_rows,  num_cols), dtype=object)
    occupied_locations = set()

    # Generate locations
    for r in range(num_rows):
        for c in range(num_cols):
            loc = location_type(f"f{r}-{c}f")
            locations_in_grid[r, c] = loc
            objects.add(loc)

    # Add connections
    for r in range(num_rows):
        for c in range(num_cols):
            loc = locations_in_grid[r, c]
            if r > 0:
                state.add(conn(loc, locations_in_grid[r-1, c], 'up'))
            if r < num_rows - 1:
                state.add(conn(loc, locations_in_grid[r+1, c], 'down'))
            if c > 0:
                state.add(conn(loc, locations_in_grid[r, c-1], 'left'))
            if c < num_cols - 1:
                state.add(conn(loc, locations_in_grid[r, c+1], 'right'))

    # Add robot
    robot = robot_type("robot0")
    objects.add(robot)
    state.add(handsfree(robot))
    
    # Get robot location
    if randomize_robot_start:
        loc = get_random_location(locations_in_grid)
    else:
        loc = locations_in_grid[0, 0]
    occupied_locations.add(loc)
    state.add(robot_at(robot, loc))

    # Add hospital
    hospital = hospital_type("hospital0")
    objects.add(hospital)

    # Get hospital loc
    if randomize_hospital_loc:
        hospital_loc = get_random_location(locations_in_grid)
    else:
        hospital_loc = locations_in_grid[-1, -1]
    occupied_locations.add(hospital_loc)
    state.add(hospital_at(hospital, hospital_loc))

    # Add people
    people = []
    for person_idx in range(num_people):
        person = person_type(f"person{person_idx}")
        objects.add(person)
        people.append(person)

    # Get people locations
    for person_idx, person in enumerate(people):
        if randomize_person_loc:
            loc = get_random_location(locations_in_grid)
        else:
            loc = get_random_location(locations_in_grid, 
                rng=np.random.RandomState(123+person_idx))
        occupied_locations.add(loc)
        state.add(person_at(person, loc))

    # Generate walls
    if randomize_walls:
        wall_rng = np.random
    else:
        wall_rng =  np.random.RandomState(0)
    wall_mask = wall_rng.uniform(size=(num_rows, num_cols)) < wall_probability

    wall_idx = 0
    for r in range(num_rows):
        for c in range(num_cols):
            loc = locations_in_grid[r, c]
            # Don't allow walls at occupied locs
            if loc not in occupied_locations and wall_mask[r, c]:
                wall = wall_type(f"wall{wall_idx}")
                wall_idx += 1
                objects.add(wall)
                state.add(wall_at(wall, loc))
            else:
                state.add(clear(loc))

    # Generate actions
    for person in people:
        state.add(pickup(person))
    state.add(dropoff())
    for direction in domain.constants:
        state.add(move(direction))

    return objects, state, people, hospital_loc

def create_goal(domain, people, hospital_loc, num_selected_people=1):
    person_at = domain.predicates['person-at']
    goal_lits = []
    selected_people = np.random.choice(people, size=num_selected_people, replace=False)
    for person in selected_people:
        goal_lits.append(person_at(person, hospital_loc))
    return LiteralConjunction(goal_lits)

def sample_problem(domain, problem_dir, problem_outfile, 
                   num_rows=10, num_cols=10,
                   num_people=1, num_selected_people=1,
                   randomize_person_loc=False,
                   randomize_robot_start=True,
                   wall_probability=0.05,
                   randomize_walls=False,
                   randomize_hospital_loc=False):
    
    all_objects, initial_state, people, hospital_loc = sample_state(domain, 
        num_rows=num_rows, num_cols=num_cols,
        num_people=num_people,
        randomize_person_loc=randomize_person_loc,
        randomize_robot_start=randomize_robot_start,
        wall_probability=wall_probability,
        randomize_walls=randomize_walls,
        randomize_hospital_loc=randomize_hospital_loc,
    )

    goal = create_goal(domain, people, hospital_loc, 
        num_selected_people=num_selected_people)

    filepath = os.path.join(PDDLDIR, problem_dir, problem_outfile)

    PDDLProblemParser.create_pddl_file(
        filepath,
        objects=all_objects,
        initial_state=initial_state,
        problem_name=DOMAIN_NAME,
        domain_name=domain.domain_name,
        goal=goal,
        fast_downward_order=True,
    )
    print("Wrote out to {}.".format(filepath))
    problem_id = (frozenset(initial_state), goal)
    return problem_id, filepath

def problem_is_valid(domain, problem_filepath):
    # Verify that plan can be found
    plan = run_ff(domain.domain_fname, problem_filepath)
    return len(plan) > 0

def generate_problems(num_train=50, num_test=10):
    domain = PDDLDomainParser(os.path.join(PDDLDIR, f"{DOMAIN_NAME}.pddl"),
        expect_action_preds=False,
        operators_as_actions=True)

    # Make sure problems are unique
    seen_problem_ids = set()

    problem_idx = 0
    while problem_idx < num_train + num_test:
        if problem_idx < num_train:
            problem_dir = DOMAIN_NAME
        else:
            problem_dir = f"{DOMAIN_NAME}_test"
        problem_outfile = f"problem{problem_idx}.pddl"
        problem_id, problem_filepath = sample_problem(domain, problem_dir, problem_outfile)
        if problem_id in seen_problem_ids:
            continue
        seen_problem_ids.add(problem_id)
        if problem_is_valid(domain, problem_filepath):
            problem_idx += 1


if __name__ == "__main__":
    generate_problems()