# =============================================================================
# Testbed for dynamic foraging task modeling
# =============================================================================
# = Initially modified from the code for Sutton & Barto's RL book, Chapter 02
#   1. 10-bandit --> 2-bandit problem
#   2. Introducing "baiting" property
#   3. Baiting dynamics reflects in the reward probability rather than reward amplitude
#
# = Forager types:
#   1. Special foragers
#       1). 'Random'
#       2). 'LossCounting': switch to another option when loss count exceeds a threshold drawn from Gaussian [from Shahidi 2019]
#           - 3.1: loss_count_threshold = inf --> Always One Side
#           - 3.2: loss_count_threshold = 1 --> win-stay-lose-switch
#           - 3.3: loss_count_threshold = 0 --> Always switch
#       3). 'IdealpGreedy': knows p_reward + always chooses the largest one
#       4). 'IdealpHatGreedy': knows p_reward AND p_hat + always chooses the largest one p_hat ==> {m,1}, analytical
#       5). 'IdealpHatOptimal': knows p_reward AND p_hat + always chooses the REAL optimal ==> {m,n}, no analytical solution
#       6). 'AmB1': repeat the pattern AMB1, e.g., if m = 4, AAAABAAAAB, across all session
#       7). 'pMatching': to show that pMatching is necessary but not sufficient
#
#   2. NLP-like foragers
#       1). 'Sugrue2004':        income  ->   exp filter   ->  fractional                   -> epsilon-Poisson (epsilon = 0 in their paper; I found it essential)
#       2). 'Corrado2005':     income  ->  2-exp filter  ->  softmax ( = diff + sigmoid)  -> epsilon-Poisson (epsilon = 0 in their paper; has the same effect as tau_long??)
#       3). 'Iigaya2019':      income  ->  2-exp filter  ->  fractional                   -> epsilon-Poisson (epsilon = 0 in their paper; has the same effect as tau_long??)
#
#   3. RL-like foragers
#       1). 'SuttonBartoRLBook': return  ->   exp filter                                    -> epsilon-greedy  (epsilon > 0 is essential)
#       2). 'Bari2019':        return/income  ->   exp filter (both forgetting)   -> softmax     -> epsilon-Poisson (epsilon = 0 in their paper, no necessary)
#       3). 'Hattori2019':     return/income  ->   exp filter (choice-dependent forgetting, reward-dependent step_size)  -> softmax  -> epsilon-Poisson (epsilon = 0 in their paper; no necessary)
#
#   
# = About epsilon (the probability of making a random choice on each trial):
#  - Epsilon is a simple way of encouraging exploration. There is virtually no cost -- just be lazy. (see Sutton&Barto's RL book, p.28)
#  - 'Sugrue 2004' and 'Iigaya2019' needs explicit exploration, because they use fractional income (could incorrectly converge to 1, resulting in making the same choice forever). 
#     In contrast, Corrado 2005 may not need this, because softmax will prevent this.
#  - 'Iigaya2019' can be (partly) rescued by random_before_total_reward, because it has a long time constant. 
#     After some explicit exploration at the beginning of a session, the tau_long component actually prevent the choice probability to be fixed at 1.
#  - However, random_before_total_reward cannot help 'Sugrue2004', because it only has one fast tau. 
#     'Sugrue2004' definitely needs epsilon, which effectively sets a maximum choice probability of 1-epsilon/2.
#
#
# Feb 2020, Han Hou (houhan@gmail.com) @ Houston 
# Svoboda & Li lab
# =============================================================================

#######################################################################
# Copyright (C)                                                       #
# 2016-2018 Shangtong Zhang(zhangshangtong.cpp@gmail.com)             #
# 2016 Tian Jun(tianjun.cpp@gmail.com)                                #
# 2016 Artem Oboturov(oboturov@gmail.com)                             #
# 2016 Kenta Shimada(hyperkentakun@gmail.com)                         #
# Permission given to modify the code as long as you keep this        #
# declaration at the top                                              #
#######################################################################


import numpy as np

LEFT = 0
RIGHT = 1

global_block_size_mean = 80
global_block_size_sd = 20

def softmax(x,softmax_temperature):
    max_temp = np.max(x/softmax_temperature)
    
    if np.exp(max_temp) == np.inf:  # To prevent explosion of EXP
        greedy = np.zeros(len(x))
        greedy[np.random.choice(np.where(x == np.max(x))[0])] = 1
        return greedy
    else:   # Normal softmax
        return np.exp(x/softmax_temperature)/np.sum(np.exp(x/softmax_temperature))  # Accept np.arrays


class Bandit:
    
    # @k_arm: # of arms
    # @epsilon: probability for exploration in epsilon-greedy algorithm
    # @initial: initial estimation for each action
    # @step_size: constant step size for updating estimations
    
    def __init__(self, forager = 'SuttonBartoRLBook', k_arm = 2, n_trials = 1000, if_baited = True, if_para_optim = False,
                 epsilon = 0,          # Essential for 'SuttonBartoRLBook', 'Sugrue 2004', 'Iigaya2019'. See notes above.
                 random_before_total_reward = 0, # Not needed by default. See notes above
                 softmax_temperature = np.nan,   # For 'Bari2019', 'Hattori2019','Corrado2005'
                 
                 taus = 20,        # For 'Sugrue2004' (only one tau is needed), 'Corrado2005', 'Iigaya2019'. Could be any number of taus, e.g., [2,15]
                 w_taus = 1,       # For 'Sugrue2004' (w_tau = 1), 'Corrado2005', 'Iigaya2019'.              Could be any number of taus, e.g., [0.3, 0.7]
                 
                 step_sizes = 0.1,      # For 'SuttonBartoRLBook'， 'Bari2019'， 'Hattori2019' (step_sizes = [unrewarded step_size, rewarded step_size]).
                 forget_rate = 0,      # For 'SuttonBartoRLBook' (= 0)， 'Bari2019' (= 1-Zeta)， 'Hattori2019' ( = unchosen_forget_rate).
                 
                 loss_count_threshold_mean = 3,   # For 'LossCounting' [from Shahidi 2019]
                 loss_count_threshold_std = 1,    # For 'LossCounting' [from Shahidi 2019]
                 
                 p_reward_seed_override = '',  # If true, use the same random seed for generating p_reward!!
                 p_reward_sum = 0.45,   # Gain of reward. Default = 0.45
                 p_reward_pairs = None,  # Full control of reward prob
                 
                 m_AmB1 = 1,  # For choice pattern {AmB1}
                 ):     

        self.forager = forager
        self.k = k_arm
        self.n_trials = n_trials
        self.if_baited = if_baited
        self.if_para_optim = if_para_optim
        
        self.epsilon = epsilon
        self.random_before_total_reward = random_before_total_reward
        self.softmax_temperature = softmax_temperature
        self.loss_count_threshold_mean = loss_count_threshold_mean
        self.loss_count_threshold_std = loss_count_threshold_std
        self.p_reward_seed_override = p_reward_seed_override
        self.p_reward_sum = p_reward_sum
        self.p_reward_pairs = p_reward_pairs
        self.m_AmB1 = m_AmB1
            
        if forager == 'Sugrue2004':
            self.taus = [taus]
            self.w_taus = [w_taus]
        else:
            self.taus = taus
            self.w_taus = w_taus

        
        # Turn step_size and forget_rate into reward- and choice- dependent, respectively. (for 'Hattori2019')
        if forager == 'SuttonBartoRLBook':
            self.step_sizes = [step_sizes] * 2  # Replication
            self.forget_rates = [0, 0]   # Override
        elif forager == 'Bari2019':
            self.step_sizes = [step_sizes] * 2
            self.forget_rates = [forget_rate, forget_rate]
        elif forager == 'Hattori2019':
            self.step_sizes = step_sizes            # Should be [unrewarded step_size, rewarded_step_size] by itself
            self.forget_rates = [forget_rate, 0]   # Only unchosen target is forgetted
          
    def reset(self):
        
        #  print(self)
        
        # Initialization
        self.time = 0
        self.choice_history = np.zeros([1,self.n_trials])  # Choice history
        self.q_estimation = np.zeros([self.k, self.n_trials]) # Estimation for each action (e.g., Q in Bari2019, L-stage scalar value in Corrado2005) 
        self.choice_prob = np.zeros([self.k, self.n_trials]) # Estimation for each action (e.g., Q in Bari2019, L-stage scalar value in Corrado2005) 
        self.reward_history = np.zeros([self.k, self.n_trials])    # Reward history, separated for each port (Corrado Newsome 2005)
        
        # Generate baiting prob in block structure
        self.generate_p_reward()
        
        # Prepare reward for the first trial
        # For example, [0,1] represents there is reward baited at the RIGHT but not LEFT port.
        self.reward_available = np.zeros([self.k, self.n_trials])    # Reward history, separated for each port (Corrado Newsome 2005)
        self.reward_available[:,0] = (np.random.uniform(0,1,self.k) < self.p_reward[:, self.time]).astype(int)
        
        # Forager-specific
        if self.forager in ['SuttonBartoRLBook', 'Bari2019', 'Hattori2019']:
            effective_taus = -1/np.log(1-(np.array(self.step_sizes) + np.array(self.forget_rates)))
            
            self.description = '%s, step_sizes = %s (tau_eff = %s), forget = %s, softmax_temp = %g, epsi = %g' % \
                               (self.forager, np.round(np.array(self.step_sizes),3), np.round(effective_taus,3), self.forget_rates, self.softmax_temperature, self.epsilon)
                               
            self.choice_prob[:] = 1/self.k   # To be strict
 
        elif self.forager in ['Sugrue2004', 'Corrado2005', 'Iigaya2019']:
            self.description = '%s, taus = %s, w_taus = %s, softmax_temp = %g, epsi = %g, random_before_total_reward = %g' % \
                                            (self.forager, np.round(self.taus,3), np.round(self.w_taus,3), np.round(self.softmax_temperature,3), np.round(self.epsilon,3), 
                                             self.random_before_total_reward)
                                            
            # Compute the history filter. Compatible with any number of taus.
            reversed_t = np.flipud(np.arange(self.n_trials))  # Use the full length of the session just in case of an extremely large tau.
            self.history_filter = np.zeros_like(reversed_t).astype('float64')
            
            for tau, w_tau in zip(self.taus, self.w_taus):
                self.history_filter += w_tau * np.exp(-reversed_t / tau) / np.sum(np.exp(-reversed_t / tau))  # Note the normalization term (= tau when n -> inf.)
            
            self.choice_prob[:] = 1/self.k   # To be strict
            
        elif self.forager in ['LossCounting']:
            self.description = '%s, loss_thres +/- std = %g +/- %g' % (self.forager, self.loss_count_threshold_mean, self.loss_count_threshold_std)
            
            # Initialize
            self.loss_count = np.zeros([1, self.n_trials]) 
            self.loss_threshold_this = np.random.normal(self.loss_count_threshold_mean, self.loss_count_threshold_std)

        else:
            self.description = self.forager
            
    def generate_p_reward(self, block_size_base = global_block_size_mean, 
                                block_size_sd = global_block_size_sd,
                                p_reward_pairs = [[.4,.05],[.3857,.0643],[.3375,.1125],[.225,.225]],  # (Bari-Cohen 2019)  
                         ):  
        
        # If para_optim, fix the random seed to ensure that p_reward schedule is fixed for all candidate parameters
        # However, we should make it random during a session (see the last line of this function)
        if self.p_reward_seed_override != '':
            np.random.seed(self.p_reward_seed_override)
            
        if self.p_reward_pairs == None:            
            p_reward_pairs = np.array(p_reward_pairs) / 0.45 * self.p_reward_sum
        else:  # Full override of p_reward
            p_reward_pairs = self.p_reward_pairs
                
        # Adapted from Marton's code
        n_trials_now = 0
        block_size = []  
        p_reward = np.zeros([2,self.n_trials])
        
        self.rewards_IdealpHatOptimal = 0
        self.rewards_IdealpHatGreedy = 0
        
        # Fill in trials until the required length
        while n_trials_now < self.n_trials:
        
            # Number of trials in each block (Gaussian distribution)
            # I treat p_reward[0,1] as the ENTIRE lists of reward probability. RIGHT = 0, LEFT = 1. HH
            n_trials_this_block = np.rint(np.random.normal(block_size_base, block_size_sd)).astype(int) 
            n_trials_this_block = min(n_trials_this_block, self.n_trials - n_trials_now)
            
            block_size.append(n_trials_this_block)
                              
            # Get values to fill for this block
            if n_trials_now == -1:  # If 0, the first block is set to 50% reward rate (as Marton did)
                p_reward_this_block = np.array([[sum(p_reward_pairs[0])/2] * 2])  # Note the outer brackets
            else:
                # Choose reward_ratio_pair
                if n_trials_now > 0 and not(np.diff(p_reward_this_block)):   # If we had equal p_reward in the last block
                    pair_idx = np.random.choice(range(len(p_reward_pairs)-1))   # We should not let it happen again immediately
                else:
                    pair_idx = np.random.choice(range(len(p_reward_pairs)))
                    
                p_reward_this_block = np.array([p_reward_pairs[pair_idx]])   # Note the outer brackets, otherwise cannot be broadcast below

                # To ensure flipping of p_reward during transition (Marton)
                if len(block_size) % 2:     
                    p_reward_this_block = np.flip(p_reward_this_block)
                
            # Fill in trials for this block
            p_reward[:, n_trials_now : n_trials_now + n_trials_this_block] = p_reward_this_block.T
            
            # Fill choice history for some special foragers with choice patterns {AmBn} (including IdealpHatOptimal, IdealpHatGreedy, and AmB1)
            self.get_AmBn_choice_history(p_reward_this_block, n_trials_this_block, n_trials_now)
                            
            # Next block
            n_trials_now += n_trials_this_block 
        
        self.n_blocks = len(block_size)
        self.p_reward = p_reward
        self.block_size  = np.array(block_size)
        self.p_reward_fraction = p_reward[RIGHT,:] / (np.sum(p_reward, axis = 0))   # For future use
        self.p_reward_ratio = p_reward[RIGHT,:] / p_reward[LEFT,:]   # For future use
        
        # We should make it random afterwards
        np.random.seed()
        
        
    def get_AmBn_choice_history(self, p_reward_this_block, n_trials_this_block, n_trials_now):
        
        if not self.if_para_optim:  
            # Calculate theoretical upper bound (ideal-p^-optimal) and the (fixed) choice history/matching point of it
            # Ideal-p^-Optimal
            mn_star_pHatOptimal, p_star_pHatOptimal = self.get_IdealpHatOptimal_strategy(p_reward_this_block[0])
            self.rewards_IdealpHatOptimal += p_star_pHatOptimal * n_trials_this_block
        
        # Ideal-p^-Greedy
        mn_star_pHatGreedy, p_star_pHatGreedy = self.get_IdealpHatGreedy_strategy(p_reward_this_block[0])
        self.rewards_IdealpHatGreedy += p_star_pHatGreedy * n_trials_this_block
        
        if self.forager in ['IdealpHatOptimal','IdealpHatGreedy','AmB1']:
            # Get actual {m,n}
            if self.forager == 'IdealpHatOptimal':
                mn_star = mn_star_pHatOptimal
            elif self.forager == 'IdealpHatGreedy':
                mn_star = mn_star_pHatGreedy
            elif self.forager == 'AmB1':
                mn_star = [self.m_AmB1, 1]
            
            # For ideal optimal, given p_0(t) and p_1(t), the optimal choice history is fixed, i.e., {m_star, 1} (p_min > 0)
            S = int(np.ceil(n_trials_this_block/(mn_star[0] + mn_star[1])))
            c_max_this = np.argwhere(p_reward_this_block[0] == np.max(p_reward_this_block))[0]  # To handle the case of p0 = p1
            c_min_this = np.argwhere(p_reward_this_block[0] == np.min(p_reward_this_block))[-1]
            c_star_this_block = ([c_max_this] * mn_star[0] + [c_min_this] * mn_star[1]) * S    # Choice pattern of {m_star, 1}
            c_star_this_block = c_star_this_block[:n_trials_this_block]     # Truncate to the correct length
            
            self.choice_history[0, n_trials_now : n_trials_now + n_trials_this_block] = c_star_this_block  # Save the optimal sequence
        
    def get_IdealpHatOptimal_strategy(self, p_reward):
        '''
        Theoretical upper bound of total rewards collected by the ideal-p^-optimal forager (for 2-arm task)  03/29/2020
        Unfortunately, there's no analytical solution to this, has to do a brutal search. Although n_star is likely to always be 1.
        '''
        m_max = 100  # Max search range
        n_max = 10   # We don't need much n_max, actually n should be 1.
        
        p1 = np.max(p_reward)
        p0 = np.min(p_reward)
        
        p_star = 0  # Cache of the current best p_star
        
        for m in range(1, m_max + 1):
            for n in range(1, n_max + 1):
                p_this = (2+(m-1)*p1+(n-1)*p0-(1-p1)**(n+1)-(1-p0)**(m+1))/(m+n)
                if p_this > p_star:
                    m_star = m
                    n_star = n
                    p_star = p_this
       
        return [m_star, n_star], p_star
        

    def get_IdealpHatGreedy_strategy(self, p_reward):
        '''
        Ideal-p^-greedy, only care about the current p^, which is good enough (for 2-arm task)  03/28/2020
        '''
        p_max = np.max(p_reward)
        p_min = np.min(p_reward)
        
        if p_min > 0:
            m_star = np.floor(np.log(1-p_max)/np.log(1-p_min))
            p_star = p_max + (1-(1-p_min)**(m_star + 1)-p_max**2)/(m_star+1)  # Still stands even m_star = *
    
            return [int(m_star),1], p_star
        else:
            return [self.n_trials,1], p_max   # Safe to be always on p_max side for this block
        
    def choose_ps(self, ps):
        '''
        "Poisson"-choice process
        '''
        ps = ps/np.sum(ps)
        return np.max(np.argwhere(np.hstack([-1e-16, np.cumsum(ps)]) < np.random.rand()))

    def act(self):
        # =============================================================================
        #  Update value estimation (or Poisson choice probability)
        # =============================================================================
        # = Forager types:
        #   1. Special foragers
        #       1). 'Random'
        #       2). 'LossCounting': switch to another option when loss count exceeds a threshold drawn from Gaussian [from Shahidi 2019]
        #           - 3.1: loss_count_threshold = inf --> Always One Side
        #           - 3.2: loss_count_threshold = 1 --> win-stay-lose-switch
        #           - 3.3: loss_count_threshold = 0 --> Always switch
        #       3). 'IdealpGreedy': knows p_reward + always chooses the largest one
        #       4). 'IdealpHatGreedy': knows p_reward AND p_hat + always chooses the largest one p_hat ==> {m,1}, analytical
        #       5). 'IdealpHatOptimal': knows p_reward AND p_hat + always chooses the REAL optimal ==> {m,n}, no analytical solution
        #       6). 'pMatching': to show that pMatching is necessary but not sufficient
        #
        #   2. NLP-like foragers
        #       1). 'Sugrue2004':        income  ->   exp filter   ->  fractional                   -> epsilon-Poisson (epsilon = 0 in their paper; I found it essential)
        #       2). 'Corrado2005':     income  ->  2-exp filter  ->  softmax ( = diff + sigmoid)  -> epsilon-Poisson (epsilon = 0 in their paper; has the same effect as tau_long??)
        #       3). 'Iigaya2019':      income  ->  2-exp filter  ->  fractional                   -> epsilon-Poisson (epsilon = 0 in their paper; has the same effect as tau_long??)
        #
        #   3. RL-like foragers
        #       1). 'SuttonBartoRLBook': return  ->   exp filter                                    -> epsilon-greedy  (epsilon > 0 is essential)
        #       2). 'Bari2019':        return/income  ->   exp filter (both forgetting)   -> softmax     -> epsilon-Poisson (epsilon = 0 in their paper, no necessary)
        #       3). 'Hattori2019':     return/income  ->   exp filter (choice-dependent forgetting, reward-dependent step_size)  -> softmax  -> epsilon-Poisson (epsilon = 0 in their paper; no necessary)
               
        if self.forager == 'Random': 
            choice = np.random.choice(self.k)
            
        elif self.forager == 'AlwaysLEFT':
            choice = LEFT
            
        elif self.forager in ['IdealpHatOptimal','IdealpHatGreedy','AmB1']:   # Foragers that have the pattern {AmBn}
            choice = self.choice_history[0, self.time]  # Already saved in the optimal sequence
            
        elif self.forager == 'pMatching':  # Probability matching of base probabilities p
            choice = self.choose_ps(self.p_reward[:,self.time])
            
        elif self.forager == 'LossCounting':
            if self.time == 0:
                choice = np.random.choice(self.k)  # Random on the first trial
            else:
                # Retrieve the last choice
                last_choice = self.choice_history[0, self.time - 1]
                
                if self.loss_count[0, self.time] >= self.loss_threshold_this:
                    # Switch
                    choice = LEFT + RIGHT - last_choice
                    
                    # Reset loss counter threshold
                    self.loss_count[0, self.time] = - self.loss_count[0, self.time] # A flag of "switch happens here"
                    self.loss_threshold_this = np.random.normal(self.loss_count_threshold_mean, self.loss_count_threshold_std)
                else:
                    # Stay
                    choice = last_choice
            
        elif self.forager == 'IdealpGreedy':
            choice = np.random.choice(np.where(self.p_reward[:,self.time] == self.p_reward[:,self.time].max())[0])
                
        else:
            if np.random.rand() < self.epsilon or np.sum(self.reward_history) < self.random_before_total_reward: 
                # Forced exploration with the prob. of epsilon (to avoid AlwaysLEFT/RIGHT in Sugrue2004...)
                choice = np.random.choice(self.k)
                
            else:   # Forager-dependent
                if self.forager == 'SuttonBartoRLBook':   # Greedy
                    choice = np.random.choice(np.where(self.q_estimation[:, self.time] == self.q_estimation[:, self.time].max())[0])
                    
                elif self.forager in ['Sugrue2004', 'Corrado2005', 'Iigaya2019', 'Bari2019', 'Hattori2019' ]:   # Poisson
                    #  choice = self.choose_ps(self.q_estimation[:,self.time])    
                    choice = self.choose_ps(self.choice_prob[:,self.time])    
                
        self.choice_history[0, self.time] = int(choice)
        
        return int(choice)
    
    def step(self, choice):
           
        # =============================================================================
        #  Generate reward and make the state transition (i.e., prepare reward for the next trial) --
        # =============================================================================
        reward = self.reward_available[choice, self.time]    
        self.reward_history[choice, self.time] = reward   # Note that according to Sutton & Barto's convention,
                                                          # this update should belong to time t+1, but here I use t for simplicity.
        
        reward_available_after_choice = self.reward_available[:, self.time].copy()  # An intermediate reward status. Note the .copy()!
        reward_available_after_choice [choice] = 0   # The reward is depleted at the chosen lick port.
        
        self.time += 1   # Time ticks here !!!
        if self.time == self.n_trials: 
            return;   # Session terminates
        
        # For the next reward status, the "or" statement ensures the baiting property, gated by self.if_baited.
        self.reward_available[:, self.time] = np.logical_or(  reward_available_after_choice * self.if_baited,    
                                           np.random.uniform(0,1,self.k) < self.p_reward[:,self.time]).astype(int)  
            
        # =============================================================================
        #  Update value estimation (or Poisson choice probability)
        # =============================================================================
        # = Forager types:
        #   1. Special foragers
        #       1). 'Random'
        #       2). 'LossCounting': switch to another option when loss count exceeds a threshold drawn from Gaussian [from Shahidi 2019]
        #           - 3.1: loss_count_threshold = inf --> Always One Side
        #           - 3.2: loss_count_threshold = 1 --> win-stay-lose-switch
        #           - 3.3: loss_count_threshold = 0 --> Always switch
        #       3). 'IdealpGreedy': knows p_reward + always chooses the largest one
        #       4). 'IdealpHatGreedy': knows p_reward AND p_hat + always chooses the largest one p_hat ==> {m,1}, analytical
        #       5). 'IdealpHatOptimal': knows p_reward AND p_hat + always chooses the REAL optimal ==> {m,n}, no analytical solution
        #       6). 'pMatching': to show that pMatching is necessary but not sufficient
        #
        #   2. NLP-like foragers
        #       1). 'Sugrue2004':        income  ->   exp filter   ->  fractional                   -> epsilon-Poisson (epsilon = 0 in their paper; I found it essential)
        #       2). 'Corrado2005':     income  ->  2-exp filter  ->  softmax ( = diff + sigmoid)  -> epsilon-Poisson (epsilon = 0 in their paper; has the same effect as tau_long??)
        #       3). 'Iigaya2019':      income  ->  2-exp filter  ->  fractional                   -> epsilon-Poisson (epsilon = 0 in their paper; has the same effect as tau_long??)
        #
        #   3. RL-like foragers
        #       1). 'SuttonBartoRLBook': return  ->   exp filter                                    -> epsilon-greedy  (epsilon > 0 is essential)
        #       2). 'Bari2019':        return/income  ->   exp filter (both forgetting)   -> softmax     -> epsilon-Poisson (epsilon = 0 in their paper, no necessary)
        #       3). 'Hattori2019':     return/income  ->   exp filter (choice-dependent forgetting, reward-dependent step_size)  -> softmax  -> epsilon-Poisson (epsilon = 0 in their paper; no necessary)
                
        if self.forager in ['LossCounting']:
            if self.loss_count[0, self.time - 1] < 0:  # A switch just happened
                self.loss_count[0, self.time - 1] = - self.loss_count[0, self.time - 1]  # Back to normal (Note that this = 0 in Shahidi 2019)
                if reward:
                    self.loss_count[0, self.time] = 0
                else:
                    self.loss_count[0, self.time] = 1
            else:
                if reward:
                    self.loss_count[0, self.time] = self.loss_count[0, self.time - 1]
                else:
                    self.loss_count[0, self.time] = self.loss_count[0, self.time - 1] + 1
                
        elif self.forager in ['SuttonBartoRLBook', 'Bari2019', 'Hattori2019']:    
            # Local return
            # Note 1: These three foragers only differ in how they handle step size and forget rate.
            # Note 2: It's "return" rather than "income" because the unchosen Q is not updated (when forget_rate = 0 in SuttonBartoRLBook)
            # Note 3: However, if forget_rate > 0, the unchosen one is also updated, and thus it's somewhere between "return" and "income".
            #         In fact, when step_size = forget_rate, the unchosen Q is updated by exactly the same rule as chosen Q, so it becomes exactly "income"
            
            # Reward-dependent step size ('Hattori2019')
            if reward:   
                step_size_this = self.step_sizes[1]
            else:
                step_size_this = self.step_sizes[0]
            
            # Choice-dependent forgetting rate ('Hattori2019')
            # Chosen:   Q(n+1) = (1- forget_rate_chosen) * Q(n) + step_size * (Reward - Q(n))
            self.q_estimation[choice, self.time] = (1 - self.forget_rates[1]) * self.q_estimation[choice, self.time - 1]  \
                                             + step_size_this * (reward - self.q_estimation[choice, self.time - 1])
                                                 
            # Unchosen: Q(n+1) = (1-forget_rate_unchosen) * Q(n)
            unchosen_idx = [cc for cc in range(self.k) if cc != choice]
            self.q_estimation[unchosen_idx, self.time] = (1 - self.forget_rates[0]) * self.q_estimation[unchosen_idx, self.time - 1] 
            
           
            # Softmax in 'Bari2019', 'Hattori2019'
            if self.forager in ['Bari2019', 'Hattori2019']:
                # --- The below line is erroneous!! Should not change q_estimation!! 04/08/2020 ---
                #     self.q_estimation[:, self.time] = softmax(self.q_estimation[:, self.time], self.softmax_temperature)
                self.choice_prob[:, self.time] = softmax(self.q_estimation[:, self.time], self.softmax_temperature)
            
        elif self.forager in ['Sugrue2004', 'Iigaya2019']:
            # Fractional local income
            # Note: It's "income" because the following computations do not dependent on the current ~choice~.
            
            # 1. Local income = Reward history + exp filter in Sugrue or 2-exp filter in IIgaya
            valid_reward_history = self.reward_history[:, :self.time]   # History till now
            valid_filter = self.history_filter[-self.time:]    # Corresponding filter
            local_income = np.sum(valid_reward_history * valid_filter, axis = 1)
            
            # 2. Poisson choice probability = Fractional local income
            if np.sum(local_income) == 0:
                # 50%-to-50%
                # self.q_estimation[:, self.time] = [1/self.k] * self.k
                self.choice_prob[:, self.time] = [1/self.k] * self.k
            else:
                # Local fractional income
                # self.q_estimation[:, self.time] = local_income / np.sum(local_income)
                self.choice_prob[:, self.time] = local_income / np.sum(local_income)
                
        elif self.forager == 'Corrado2005':
            # Softmaxed local income
            
            # 1. Local income = Reward history + hyperbolic (2-exps) filter
            valid_reward_history = self.reward_history[:, :self.time]   # History till now
            valid_filter = self.history_filter[-self.time:]    # Corresponding filter
            local_income = np.sum(valid_reward_history * valid_filter, axis = 1)
            
            # 2. Poisson choice probability = Softmaxed local income (Note: Equivalent to "difference + sigmoid" in [Corrado etal 2005], for 2lp case)
            # self.q_estimation[:, self.time] = softmax(local_income, self.softmax_temperature)
            self.choice_prob[:, self.time] = softmax(local_income, self.softmax_temperature)
            
        return reward
  
 