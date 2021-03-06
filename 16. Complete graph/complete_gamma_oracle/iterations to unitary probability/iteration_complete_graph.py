# M. Garbellini
# Dept. of Physics
# Universita degli Studi di Milano
# matteo.garbellini@studenti.unimi.it


import sys
import time
import numpy as np
from scipy import linalg
from scipy.integrate import odeint, solve_ivp
import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import multiprocessing as mp
import ray


# useful global variables, shouldn't be too inefficient
global dimension
global step_function
global topology
# error tolerance (relative and absolute) for RK45 intergrator
global rtolerance, atolerance


# routine to generate loop hamiltonian + oracle state
def generate_hamiltonian(dimension, beta, time, T):

    if(topology == "complete"):
        # generate laplacian
        laplacian = np.empty([dimension, dimension])
        laplacian.fill(-1)
        for i in range(dimension):
            for j in range(dimension):
                if i == j:
                    laplacian[i, j] += dimension


    elif(topology== "circular"):
        # generate diagonal matrix
        diag_matrix = np.empty([dimension, dimension])
        diag_matrix.fill(0)
        for i in range(dimension):
            for j in range(dimension):
                if i == j:
                    diag_matrix[i, j] = 2

        # generate loop adjacency matrix
        adj_matrix = np.empty([dimension, dimension])
        adj_matrix.fill(0)
        for i in range(dimension):
            for j in range(dimension):
                if (i == j):
                    if (i == 0 & j == 0):
                        adj_matrix[i, dimension - 1] = 1
                        adj_matrix[i, j + 1] = 1
                    elif (i == (dimension - 1) & j == (dimension - 1)):
                        adj_matrix[i, j - 1] = 1
                        adj_matrix[i, 0] = 1
                    else:
                        adj_matrix[i, j - 1] = 1
                        adj_matrix[i, j + 1] = 1

        # generate laplacian of loop
        laplacian = diag_matrix - adj_matrix
    else:
        print("Error: undefined topology")


    # generate time-stepping function g_T(t): let's consider three cases, ^1, ^1/2, 1^1/3
    # Note: if t=0 the function is automatically set to 'almost zero' (0.000001). This prevents warning within the ODE solver
    if(time == 0 or T == 0):
        hamiltonian = laplacian
    else:
        if(step_function == 'lin'):
            g_T = float(time) / T
        elif(step_function == 'sqrt'):
            g_T = np.sqrt(float(time) / T)
        elif(step_function == 'cbrt'):
            g_T = np.cbrt(float(time) / T)
        elif(step_function == 'cerf_3'):
            nn = np.sqrt(-1 + dimension)
            g_T = 0.5 * (1 + (2 * (float(time) / T) - 1)**3)
        elif(step_function == 'cerf_5'):
            g_T = 0.5 * (1 + (2 * (float(time) / T) - 1)**5)
        elif(step_function == 'cerf_7'):
            g_T = 0.5 * (1 + (2 * (float(time) / T) - 1)**7)

        else:
            print("Error: step_function value not defined")

        # generate time dependet hamiltonian
        hamiltonian = (1 - g_T) *laplacian

        # generate problem_hamiltonian (i.e. adding oracle to central site)
        hamiltonian[int((dimension - 1) / 2),
                    int((dimension - 1) / 2)] += - g_T*beta

    return hamiltonian

def generate_time_independent_hamiltonian(dimension, gamma):
    #generate diagonal matrix
    diag_matrix = np.empty([dimension, dimension])
    diag_matrix.fill(0)
    for i in range(dimension):
        for j in range(dimension):
            if i == j:

                diag_matrix[i][j] = 2
                if(topology == 'complete'):
                    diag_matrix[i][j] = dimension
            else:
                diag_matrix[i][j] = 0

    #generate loop adjacency matrix
    adj_matrix = np.empty([dimension, dimension])
    adj_matrix.fill(0)
    for i in range(dimension): #colonna
        for j in range(dimension): #riga
            if i == j:
                if i == 0 & j == 0:
                    adj_matrix[i][dimension-1] = 1
                    adj_matrix[i][j+1] = 1
                elif i == dimension-1 & j == dimension-1:
                    adj_matrix[i][j-1] = 1
                    adj_matrix[i][0] = 1
                else:
                    adj_matrix[i][j-1] = 1
                    adj_matrix[i][j+1] = 1


    #generate laplacian of loop
    hamiltonian = (diag_matrix - adj_matrix)

    #generate problem_hamiltonian (i.e. adding oracle tipical energy to center site)
    index = int((dimension-1)/2)
    hamiltonian[index][index] += - gamma

    #complete graph hamiltonian
    hamiltonian_complete = np.empty([dimension, dimension])
    hamiltonian_complete.fill(-1)
    for i in range(dimension):
        hamiltonian_complete[i][i] += dimension

    index = int((dimension-1)/2)
    hamiltonian_complete[index][index] += - gamma


    return hamiltonian_complete


# routine to implement schroedinger equation. returns d/dt(psi)
# for the ODE solver
def schrodinger_equation(t, y, beta, T):

    H = generate_hamiltonian(dimension, beta, t, T)
    derivs = []
    psi = 0
    for i in range(dimension):
        for j in range(dimension):
            psi += H[i, j] * y[j]
        derivs.append(-1j * psi)
        psi = 0

    return derivs

# schroedinger equation solver. returns psi(t)
def solve_schrodinger_equation(time, beta):

    y0 = np.empty(dimension, dtype=complex)
    y0.fill(1 / (np.sqrt(dimension)))

    sh_solved = solve_ivp(schrodinger_equation, [0., time], y0, method='RK45', atol=atolerance, rtol=rtolerance, args=(beta, time))
    # for more precise results use method RK45 and max_step=t_step_max
    # for less precise results but faster computation use 'BDF'
    psi_t = np.empty(dimension, dtype=complex)
    for i in range(dimension):
        psi_t[i] = sh_solved.y[i, len(sh_solved.y[i]) - 1]

    normalization = np.dot(np.conj(psi_t), psi_t)
    return psi_t*(1/np.sqrt(normalization))

# routine to evaluate probability |<w|psi(t)>|^2
def evaluate_probability(x, oracle_site_state):

    # find evolved state (already normalized)
    psi_t = solve_schrodinger_equation(x[0], x[1])

    # probability evaluation
    probability = np.dot(oracle_site_state.transpose(),psi_t)
    if(np.abs(probability)**2 > 1):
        print('Error: probability out of bounds: ', np.abs(probability)**2)
    else:
        return -np.abs(probability)**2

@ray.remote
def grid_eval(time, beta_array):

    # Define oracle site state
    oracle_site_state = np.empty([dimension, 1])
    oracle_site_state.fill(0)
    oracle_site_state[int((dimension - 1) / 2)][0] = 1

    # Define time, beta and probability and adiabatic_check array
    probability = np.empty([len(beta_array), 1])

    if(type_of_qw == 'dependent'):
        for j in range(len(beta_array)):
            probability[j][0] = -evaluate_probability([beta_array[j], time], oracle_site_state)

    return probability


def parallel_routine(lb_beta, ub_beta):

    # initialize ray multiprocessing
    ray.init()

    # useful definitions for multicore computation
    cpu_count = 4
    sampling_per_cpu_count = 6
    beta_sampling_points = cpu_count * sampling_per_cpu_count
    beta = np.linspace(lb_beta, ub_beta, beta_sampling_points)
    time = np.pi/(2*np.sqrt(dimension))
    process = []
    probability = []

    # parallel processes
    for i in range(cpu_count):
        process.append(grid_eval.remote(time, beta[int(
            sampling_per_cpu_count * i):int(sampling_per_cpu_count * (i + 1))]))

    # reassigning values to arrays
    for i in range(cpu_count):
        probability.append(ray.get(process[i]))

    # concatenate arrays to output array
    probability_array = np.concatenate(
        [probability[0], probability[1]], axis=0)
    for i in range(cpu_count - 2):
        probability_array = np.concatenate(
            [probability_array, probability[i + 2]])

    # shutting down ray
    ray.shutdown()

    max = 0
    for i in range(len(beta)):
        if(probability_array[i,0] > max):
            max = probability_array[i,0]

    print(dim, max, float(1/max))

    # preparing for export and export and miscellanea
    if(type_of_qw == 'dependent'):
        file_probability = str(dimension) + '_' + topology + '_probability_' + step_function + '.npy'
    else:
        file_probability = str(dimension) + '_' + topology + '_probability_static.npy'

    file_beta = str(dimension) + '_complete_beta.npy'


    np.save(file_probability, probability_array)
    np.save(file_beta, beta)


    return 0


if __name__ == '__main__':


    print('\n \n \t*  *  *  *  *  *  *  *  *  *  *  *  *  *  *  *  *  *  *  *  *  *')
    print('\t*  Quantum Search on Graph with time-dependent Quantum Walks   *')
    print('\t*  M. Garbellini, Dept. of Physics, University of Milan        *')
    print('\t*  *  *  *  *  *  *  *  *  *  *  *  *  *  *  *  *  *  *  *  *  *\n')


    #dimensions = [5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29, 31, 33, 35, 37, 39, 41, 43, 45, 47, 49, 51]
    dimensions = [31, 41, 51]

    type_of_qw = 'dependent'
    topology = 'complete'

    rtolerance = 1e-6
    atolerance = 1e-6
    step_functions = ['static','lin', 'sqrt', 'cbrt', 'cerf_3', 'cerf_5', 'cerf_7']

    #dimension = int(sys.argv[1])
    #step_function = step_functions[step_function_index]

    """
    for dim in dimensions:
        dimension = dim
        step_function = step_functions[4]
        parallel_routine(0, 2*dimension )
    """




    dims = [31,41,51]
    #dims = [100, 200, 300, 400, 1000]
    for dim in dims:
        step_function = step_functions[4] 
        # Define oracle site state
        dimension = dim
        oracle_site_state = np.empty([dimension, 1])
        oracle_site_state.fill(0)
        oracle_site_state[int((dimension - 1) / 2)][0] = 1
        probability = -evaluate_probability([dimension,float(np.pi/(2*np.sqrt(dimension)))], oracle_site_state)

        print(dimension,probability, 1/probability)
