# -*- coding: utf-8 -*-
"""
Created on Thu Mar 19 17:15:59 2020

@author: Han
"""

import numpy as np
import multiprocessing as mp
# import matplotlib.pyplot as plt
from tqdm import tqdm
import pickle
import sys

from models.bandit_model import BanditModel
from models.bandit_model_comparison import BanditModelComparison, MODELS
from models.fitting_functions import fit_bandit, negLL_func
from utils.plot_fitting import *
   
def fit_para_recovery(forager, para_names, para_bounds, true_paras = None, n_models = 10, n_trials = 1000, 
                      para_scales = None, para_color_code = None, para_2ds = [[0,1]], fit_method = 'DE', DE_pop_size = 16, n_x0s = 1, pool = '', **kwargs):
    
    n_paras = len(para_names)
    
    if true_paras is None:
        if_no_true_paras = True
        true_paras = np.zeros([n_paras, n_models])
    else:
        if_no_true_paras = False
        n_models = np.shape(true_paras)[1]
        
    fitted_paras = np.zeros([n_paras, n_models])

    # === Do para recovery ===        
    for n in tqdm(range(n_models), desc='Parameter Recovery, %s'%forager):
        # Generate simulated para using uniform distribution in para_bounds if not specified
        if if_no_true_paras: 
            true_paras_this = []
            for pp in range(n_paras):
                true_paras_this.append(np.random.uniform(para_bounds[0][pp], para_bounds[1][pp]))
            true_paras[:,n] = true_paras_this
            
        # Generate fake data
        choice_history, reward_history, _ = generate_fake_data(forager, para_names, true_paras[:,n], **{'n_trials': n_trials,**kwargs})
            
        # Predictive fitting
        fitting_result = fit_bandit(forager, para_names, para_bounds, choice_history, reward_history, fit_method = fit_method, DE_pop_size = DE_pop_size, n_x0s = n_x0s, pool = pool)
        fitted_paras[:,n] = fitting_result.x
    
        # print(true_paras_this, fitting_result.x)
        
    # === Plot results ===
    if fit_method == 'DE':
        fit_method = 'DE ' + '(pop_size = %g)' % DE_pop_size
    else:
        fit_method = fit_method + ' (n_x0s = %g)' % n_x0s
    
    plot_para_recovery(forager, true_paras, fitted_paras, para_names, para_bounds, para_scales, para_color_code, para_2ds, n_trials, fit_method)
    
    return true_paras, fitted_paras

def generate_true_paras(para_bounds, n_models = 5, method = 'random_uniform'):
    
    if method == 'linspace':
        p1 = np.linspace(para_bounds[0][0], para_bounds[1][0], n_models[0])
        p2 = np.linspace(para_bounds[0][1], para_bounds[1][1], n_models[1])
        pp1,pp2 = np.meshgrid(p1,p2)
        true_paras = np.vstack([pp1.flatten(), pp2.flatten()])
        
        return true_paras

    elif method == 'random_uniform':
        n_paras = len(para_bounds[0])
        
        true_paras = np.zeros([n_paras, n_models])

        for n in range(n_models):
            true_paras_this = []
            for pp in range(n_paras):
                true_paras_this.append(np.random.uniform(para_bounds[0][pp], para_bounds[1][pp]))
            true_paras[:,n] = true_paras_this
                
        return true_paras
    
def generate_fake_data(forager, para_names, true_para, n_trials = 1000, **kwargs):
    # Generate fake data
    n_paras = len(para_names)
    kwarg_this = {}
    for pp in range(n_paras):
        kwarg_this[para_names[pp]] = true_para[pp]
    
    bandit = BanditModel(forager, n_trials = n_trials, **kwarg_this, **kwargs)
    bandit.simulate()
    
    choice_history = bandit.choice_history
    reward_history = bandit.reward_history
    schedule = bandit.p_reward 
    
    return choice_history, reward_history, schedule


def compute_LL_surface(forager, para_names, para_bounds, true_para, 
                       para_2ds = [[0,1]], n_grids = None, para_scales = None, 
                       fit_method = 'DE', DE_pop_size = 16, n_x0s = 1, pool = '', n_trials = 1000, **kwargs):
    '''
    Log-likelihood landscape (Fig.3a, Wilson 2019)

    '''

    # Backward compatibility
    if para_scales is None: 
        para_scales = ['linear'] * len(para_names)
    if n_grids is None:
        n_grids = [[20,20]] * len(para_names)
    
    n_worker = int(mp.cpu_count())
    pool_surface = mp.Pool(processes = n_worker)
    para_grids = []
    
    # === 1. Generate fake data; make sure the true_paras are exactly on the grid ===
    for para_2d, n_g in zip(para_2ds, n_grids):
        
        if para_scales[para_2d[0]] == 'linear':
            p1 = np.linspace(para_bounds[0][para_2d[0]], para_bounds[1][para_2d[0]], n_g[0])
        else:
            p1 = np.logspace(np.log10(para_bounds[0][para_2d[0]]), np.log10(para_bounds[1][para_2d[0]]), n_g[0])
            
        if para_scales[para_2d[1]] == 'linear':
            p2 = np.linspace(para_bounds[0][para_2d[1]], para_bounds[1][para_2d[1]], n_g[1])
        else:
            p2 = np.logspace(np.log10(para_bounds[0][para_2d[1]]), np.log10(para_bounds[1][para_2d[1]]), n_g[1])
            
        # -- Don't do this --
        # Make sure the true_paras are exactly on the grid
        # true_para[para_2d[0]] = p1[np.argmin(np.abs(true_para[para_2d[0]] - p1))]
        # true_para[para_2d[1]] = p2[np.argmin(np.abs(true_para[para_2d[1]] - p2))]
        
        # Save para_grids
        para_grids.append([p1, p2])
        
    # === 3. Generate fake data using the adjusted true value ===
    # print('Adjusted true para on grid: %s' % np.round(true_para,3))
    choice_history, reward_history, p_reward = generate_fake_data(forager, para_names, true_para, n_trials, **kwargs)
    session_num = np.zeros_like(choice_history)[0]  # Regard as one session

    # === 4. Do fitting only once ===
    if fit_method == 'DE':
        print('Fitting using %s (pop_size = %g), pool = %s...'%(fit_method, DE_pop_size, pool!=''))
    else:
        print('Fitting using %s (n_x0s = %g), pool = %s...'%(fit_method, n_x0s, pool!=''))
    
    fitting_result = fit_bandit(forager, para_names, para_bounds, choice_history, reward_history, 
                                             fit_method = fit_method, DE_pop_size = DE_pop_size, n_x0s = n_x0s, pool = pool,
                                             if_history = True, if_predictive = True)
    
    print('  True para: %s' % np.round(true_para,3))
    print('Fitted para: %s' % np.round(fitting_result.x,3))
    print('km = %g, AIC = %g, BIC = %g\n      LPT_AIC = %g, LPT_BIC = %g' % (fitting_result.k_model, np.round(fitting_result.AIC, 3), np.round(fitting_result.BIC, 3),
                                                                             np.round(fitting_result.LPT_AIC, 3), np.round(fitting_result.LPT_BIC, 3)))
    sys.stdout.flush()
       
    # === 5. Plot fitted curve ===
    plot_session_lightweight([choice_history, reward_history, p_reward], fitting_result.predictive_choice_prob)

    # === 6. Compute LL surfaces for all pairs ===
    LLsurfaces = []
    CI_cutoff_LPTs = []
    
    for ppp,((p1, p2), n_g, para_2d) in enumerate(zip(para_grids, n_grids, para_2ds)):
           
        pp2, pp1 = np.meshgrid(p2,p1)  # Note the order

        n_scan_paras = np.prod(n_g)
        LLs = np.zeros(n_scan_paras)
        
        # Make other parameters fixed at the fitted value
        para_fixed = {}
        for p_ind, (para_fixed_name, para_fixed_value) in enumerate(zip(para_names, fitting_result.x)):
            if p_ind not in para_2d: 
                para_fixed[para_fixed_name] = para_fixed_value
        
        # -- In parallel --
        pool_results = []
        for x,y in zip(np.nditer(pp1),np.nditer(pp2)):
            pool_results.append(pool_surface.apply_async(negLL_func, args = ([x, y], forager, [para_names[para_2d[0]], para_names[para_2d[1]]], choice_history, reward_history, session_num, para_fixed, [])))
            
        # Must use two separate for loops, one for assigning and one for harvesting!   
        for nn,rr in tqdm(enumerate(pool_results), total = n_scan_paras, desc='LL_surface pair #%g' % ppp):
            LLs[nn] = - rr.get()
            
        # -- Serial for debugging --
        # for nn,(x,y) in tqdm(enumerate(zip(np.nditer(pp1),np.nditer(pp2))), total = n_scan_paras, desc='LL_surface pair #%g (serial)' % ppp):
        #     LLs[nn] = negLL_func([x, y], forager, [para_names[para_2d[0]], para_names[para_2d[1]]], choice_history, reward_history, session_num, para_fixed, [])
        
        # -- Confidence interval --
        # https://www.umass.edu/landeco/teaching/ecodata/schedule/likelihood.pdf
        CI_cutoff_LL = np.max(LLs) - 3
        CI_cutoff_LPT = np.exp(CI_cutoff_LL / n_trials)
        CI_cutoff_LPTs.append(CI_cutoff_LPT)
        
        LLs = np.exp(LLs/n_trials)  # Use likelihood-per-trial = (likehood)^(1/T)
        LLs = LLs.reshape(n_g).T
        LLsurfaces.append(LLs)
 
    
    pool_surface.close()
    pool_surface.join()

    
    # Plot LL surface and fitting history
    if fit_method == 'DE':
        fit_method = 'DE ' + '(pop_size = %g)' % DE_pop_size
    else:
        fit_method = fit_method + ' (n_x0s = %g)'%n_x0s

    plot_LL_surface(forager, LLsurfaces, CI_cutoff_LPTs, para_names, para_2ds, para_grids, para_scales, true_para, fitting_result.x, fitting_result.fit_histories, fit_method, n_trials)
    
    return

def compute_confusion_matrix(models = [1,2,3,4,5,6,7,8], n_runs = 2, n_trials = 1000, pool = '', save_file = '', save_folder = '..\\results\\'):
    if models is None:  
        models = MODELS
    elif type(models[0]) is int:
        models = [MODELS[i-1] for i in models]

    n_models = len(models)
    confusion_idx = ['AIC', 'BIC', 'log10_BF_AIC', 'log10_BF_BIC', 'best_model_AIC', 'best_model_BIC']
    confusion_results = {}
    
    confusion_results['models'] = models
    confusion_results['n_runs'] = n_runs
    confusion_results['n_trials'] = n_trials
    
    for idx in confusion_idx:
        confusion_results['raw_' + idx] = np.zeros([n_models, n_models, n_runs])
        confusion_results['raw_' + idx][:] = np.nan
    
    # == Simulation ==
    for rr in tqdm(range(n_runs), total = n_runs, desc = 'Runs'):
        for mm, this_model in enumerate(models):
            this_forager, this_para_names = this_model[0], this_model[1]
            
            # Generate para
            this_true_para = []
            for pp in this_para_names:
                this_true_para.append(generate_random_para(this_forager, pp))
            
            # Generate fake data
            choice_history, reward_history, p_reward = generate_fake_data(this_forager, this_para_names, this_true_para, n_trials = n_trials)
            
            # Do model comparison
            model_comparison = BanditModelComparison(choice_history, reward_history, p_reward , models = models)
            model_comparison.fit(pool = pool, if_verbose = False)
            
            # Save data
            for idx in confusion_idx:
                confusion_results['raw_' + idx][mm, :, rr] = model_comparison.results[idx]
    
        # == Average across runs till now ==
        for idx in confusion_idx:
            confusion_results['confusion_' + idx] = np.nanmean(confusion_results['raw_' + idx], axis = 2)
        
        # == Compute inversion matrix ==
        confusion_results['inversion_best_model_AIC'] = confusion_results['confusion_best_model_AIC'] / (1e-10 + np.sum(confusion_results['confusion_best_model_AIC'], axis = 0)) 
        confusion_results['inversion_best_model_BIC'] = confusion_results['confusion_best_model_BIC'] / (1e-10 + np.sum(confusion_results['confusion_best_model_BIC'], axis = 0))
        
        # == Save data (after each run) ==
        confusion_results['models_notations'] = model_comparison.results.para_notation
        if save_file == '':
            save_file = "confusion_results_%s_%s.p" % (n_runs, n_trials)
        
        pickle.dump(confusion_results, open(save_folder+save_file, "wb"))
        
    return
        
def generate_random_para(forager, para_name):
    # With slightly narrower range than fitting bounds in BanditModelComparison
    if para_name in 'loss_count_threshold_mean':
        return np.random.uniform(0, 30)
    if para_name in 'loss_count_threshold_std':
        return np.random.uniform(0, 5)
    if para_name in ['tau1', 'tau2']:
        return 10**np.random.uniform(0, np.log10(30)) 
    if para_name in ['w_tau1', 'learn_rate', 'learn_rate_rew', 'learn_rate_unrew', 'forget_rate', 'epsilon']:
        return np.random.uniform(0, 1)
    if para_name in 'softmax_temperature':
        return 1/np.random.exponential(10)
    if para_name in ['biasL']:
        if forager in ['Random', 'pMatching', 'RW1972_epsi']:
            return np.random.uniform(-0.45, 0.45)
        elif forager in ['RW1972_softmax', 'LNP_softmax', 'Bari2019', 'Hattori2019']:
            return np.random.uniform(-5, 5)
    return np.nan    
    

#%%
if __name__ == '__main__':
    
    # Fitting methods: 
    # - Global optimizer (`DE`): use its own parallel method
    # - Local optimizer (`L-BFGS-B`, `SLSQP`, `TNC`, `trust-constr`): random initialization in parallel
    # - Speed: L-BFGS-B = SLSQP  >> TNC >>> trust-constr
    
    n_worker = int(mp.cpu_count()/2)
    pool = mp.Pool(processes = n_worker)
    
    #%% --- Use async to run multiple initializations ---
    # Para recovery
    
    # forager = 'LossCounting'
    # para_names = ['loss_count_threshold_mean','loss_count_threshold_std']
    # para_bounds = [[0,0],[50,10]]
    
    # true_paras = generate_true_paras([[0,0],[30,5]], n_models = [5,5], method = 'linspace')
    
    # true_paras, fitted_para = fit_para_recovery(forager = forager, 
    #               para_names = para_names, para_bounds = para_bounds, 
    #               true_paras = true_paras, n_trials = n_trials, 
    #               fit_method = 'DE', pool = pool);    
    
    # # -------------------------------------------------------------------------------------------
    # n_trials = 1000

    # forager = 'LossCounting'
    # para_names = ['loss_count_threshold_mean','loss_count_threshold_std']
    # para_bounds = [[0,0],[40,0]]
    
    # # -- Para recovery
    # # true_paras = generate_true_paras([[0,0],[30,5]], n_models = [5,5], method = 'linspace')
    # # fit_para_recovery(forager = forager, 
    # #                   para_names = para_names, para_bounds = para_bounds, 
    # #                   true_paras = true_paras, n_trials = n_trials, 
    # #                   fit_method = 'L-BFGS-B', n_x0s = 1, pool = '');    
   
    # # -- LL_surface
    # compute_LL_surface(forager, para_names, para_bounds, true_para = [10,0], n_trials = n_trials, 
    #                     fit_method = 'DE', pool = pool)
    
    # # -------------------------------------------------------------------------------------------
    # n_trials = 1000

    # forager = 'LossCounting'
    # para_names = ['loss_count_threshold_mean','loss_count_threshold_std']
    # para_bounds = [[0,0],[50,10]]
    
    # # -- Para recovery
    # # true_paras = generate_true_paras([[0,0],[30,5]], n_models = [5,5], method = 'linspace')
    # # fit_para_recovery(forager = forager, 
    # #                   para_names = para_names, para_bounds = para_bounds, 
    # #                   true_paras = true_paras, n_trials = n_trials, 
    # #                   fit_method = 'L-BFGS-B', n_x0s = 1, pool = '');    
   
    # # -- LL_surface
    # compute_LL_surface(forager, para_names, para_bounds, true_para = [10,0], n_trials = n_trials, 
    #                     # fit_method = 'DE', pool = pool)
    #                     fit_method = 'L-BFGS-B', n_x0s = 1, pool = '')
    
    # -------------------------------------------------------------------------------------------
    # n_trials = 100
    
    # forager = 'LNP_softmax'
    # para_names = ['tau1','softmax_temperature']
    # para_scales = ['linear','log']
    # para_bounds = [[1e-3,1e-2],[100,15]]
    
    # # -- Para recovery
    # n_models = 20
    # true_paras = np.vstack((10**np.random.uniform(0, np.log10(30), size = n_models),
    #                         1/np.random.exponential(10, size = n_models))) # Inspired by Wilson 2019. I found beta ~ Exp(10) would be better
    
    # true_paras, fitted_para = fit_para_recovery(forager, 
    #               para_names, para_bounds, true_paras, n_trials = n_trials, 
    #               para_scales = para_scales,
    #               fit_method = 'DE', pool = pool);    
    
    # # # -- LL_surface
    # # compute_LL_surface(forager, para_names, para_bounds, para_scales = para_scales, true_para = [20, .9], n_trials = n_trials, 
    # #                     fit_method = 'DE', n_x0s = 8, pool = pool)

    # -------------------------------------------------------------------------------------------
    # n_trials = 100
    
    # forager = 'LNP_softmax'
    # para_names = ['tau1','tau2','w_tau1','softmax_temperature']
    # para_scales = ['log','log','linear','log']
    # para_bounds = [[1e-1, 1e-1, 0, 1e-2],
    #                 [15  , 40,   1,  15]]
    
    # ##-- Para recovery
    # # n_models = 1
    # # true_paras = np.vstack((10**np.random.uniform(np.log10(1), np.log10(10), size = n_models),
    # #                        10**np.random.uniform(np.log10(10), np.log10(30), size = n_models),
    # #                        np.random.uniform(0.1, 0.9, size = n_models),
    # #                        1/np.random.exponential(10, size = n_models))) # Inspired by Wilson 2019. I found beta ~ Exp(10) would be better
    # # true_paras, fitted_para = fit_para_recovery(forager, 
    # #               para_names, para_bounds, true_paras, n_trials = n_trials, 
    # #               para_scales = para_scales, para_color_code = 2, para_2ds = [[0,1],[0,2],[0,3]],
    # #               fit_method = 'DE', pool = pool);    

    # # -- LL_surface (see the gradient around Corrado 2005 results)
    # compute_LL_surface(forager, para_names, para_bounds, 
    #                     true_para = [2, 16, 0.33, 0.15], # Corrado 2005 fitting results
    #                     para_2ds = [[0,1],[0,2],[0,3],[1,2],[1,3],[2,3]], # LL surfaces for user-defined pairs of paras
    #                     n_grids = [[30,30]] * 6, 
    #                     para_scales = para_scales,
    #                     DE_pop_size = 8,
    #                     n_trials = n_trials,
    #                     fit_method = 'DE', n_x0s = 8, pool = pool)
    
    # -------------------------------------------------------------------------------------------

    # n_trials = 1000

    # forager = 'RW1972_epsi'
    # # para_names = ['learn_rate_rew','epsilon']
    # para_names = ['learn_rate','epsilon']
    # para_scales = ['linear','linear']
    # para_bounds = [[0, 0],
    #                 [1, 1]]
    
    # #-- Para recovery
    # n_models = 2
    # true_paras = np.vstack((np.random.uniform(0, 1, size = n_models),
    #                         np.random.uniform(0, 1, size = n_models),
    #                         ))
    # true_paras, fitted_para = fit_para_recovery(forager, 
    #               para_names, para_bounds, true_paras, n_trials = n_trials, 
    #               para_scales = para_scales, para_color_code = 1, para_2ds = [[0,1]],
    #               fit_method = 'DE', pool = pool);    
    
    # # # -- LL_surface --
    # # compute_LL_surface(forager, para_names, para_bounds, 
    # #                     true_para = [0.1, 0.5],
    # #                     para_2ds = [[0,1]], # LL surfaces for user-defined pairs of paras
    # #                     n_grids = [[30,30]] * 6, 
    # #                     para_scales = para_scales,
    # #                     n_trials = n_trials,
    # #                     fit_method = 'DE', n_x0s = 8, pool = pool)
    
    # # -------------------------------------------------------------------------------------------
    # n_trials = 100
    
    # forager = 'RW1972_softmax'
    # # para_names = ['learn_rate_rew','softmax_temperature']
    # para_names = ['learn_rate','softmax_temperature']
    # para_scales = ['linear','log']
    # para_bounds = [[0, 1e-2],
    #                 [1, 15]]
    
    # # # -- Para recovery
    # # n_models = 2
    # # true_paras = np.vstack((np.random.uniform(0, 1, size = n_models),
    # #                         1/np.random.exponential(10, size = n_models),
    # #                         ))
    # # true_paras, fitted_para = fit_para_recovery(forager, 
    # #               para_names, para_bounds, true_paras, n_trials = n_trials, 
    # #               para_scales = para_scales, para_color_code = 1, para_2ds = [[0,1]],
    # #               fit_method = 'DE', pool = pool);    

    # #-- LL_surface --
    # compute_LL_surface(forager, para_names, para_bounds, 
    #                     true_para = [0.1, 0.5],
    #                     para_2ds = [[0,1]], # LL surfaces for user-defined pairs of paras
    #                     n_grids = [[30,30]] * 6, 
    #                     para_scales = para_scales,
    #                     n_trials = n_trials,
    #                     fit_method = 'DE', n_x0s = 8, pool = pool)
    
    # # # -------------------------------------------------------------------------------------------
    # n_trials = 1000

    # forager = 'Bari2019'
    # # para_names = ['learn_rate_rew','forget_rate','softmax_temperature']
    # para_names = ['learn_rate','forget_rate','softmax_temperature']
    # para_scales = ['linear','linear', 'log']
    # para_bounds = [[0, 0, 1e-2],
    #                 [1, 1, 15]]
    
    # # -- LL_surface --
    # compute_LL_surface(forager, para_names, para_bounds, 
    #                     true_para = [0.1976758, 0.01164267, 0.19536022],  # Use values that optimize reward
    #                     para_2ds = [[0,1],[0,2],[1,2]], # LL surfaces for user-defined pairs of paras
    #                     n_grids = [[20,20]] * 6, 
    #                     para_scales = para_scales,
    #                     n_trials = n_trials,
    #                     fit_method = 'DE', n_x0s = 8, pool = pool)
    
    # # # -------------------------------------------------------------------------------------------
    # n_trials = 1000
    
    # forager = 'Hattori2019'
    # para_names = ['learn_rate_rew','learn_rate_unrew', 'forget_rate','softmax_temperature']
    # para_scales = ['linear','linear','linear', 'log']
    # para_bounds = [[0, 0, 0, 1e-2],
    #                 [1, 1, 0, 15]]
    
    # # #-- Para recovery
    # # n_models = 50
    # # true_paras = np.vstack((np.random.uniform(0, 1, size = n_models),
    # #                         np.random.uniform(0, 1, size = n_models),
    # #                         np.random.uniform(0, 1, size = n_models),
    # #                         1/np.random.exponential(10, size = n_models),
    # #                         ))
    # # true_paras, fitted_para = fit_para_recovery(forager, 
    # #               para_names, para_bounds, true_paras, n_trials = n_trials, 
    # #               para_scales = para_scales, para_color_code = 3, para_2ds = [[0,1],[0,2],[0,3],[1,2],[1,3],[2,3]],
    # #               fit_method = 'DE', pool = pool);    
    
    # # -- LL_surface --
    # compute_LL_surface(forager, para_names, para_bounds, 
    #                 true_para = [0.2, 0.3, 0, 0.3],
    #                 para_2ds = [[0,1],[0,2],[0,3],[1,2],[1,3],[2,3]], # LL surfaces for user-defined pairs of paras
    #                 n_grids = [[20,20]] * 6, 
    #                 para_scales = para_scales,
    #                 n_trials = n_trials,
    #                 fit_method = 'DE', n_x0s = 8, pool = pool)
    
    # n_trials = 1000
    
    # forager = 'Hattori2019_CK'
    # para_names = ['learn_rate_rew','learn_rate_unrew', 'forget_rate','softmax_temperature', 'choice_step_size','choice_softmax_temperature']
    # para_scales = ['linear','linear','linear', 'log', 'linear', 'log']
    # para_bounds = [[0, 0, 0, 1e-2, 0, 1e-2],
    #                [1, 1, 1, 15,   1, 20]]
    
    # # -- LL_surface --
    # compute_LL_surface(forager, para_names, para_bounds, 
    #                     true_para = [0.4, 0.2, 0.2, 0.25, 0.5, 1],  
    #                     para_2ds = [[0,1],[0,2],[0,3],[1,2],[1,3],[2,3]], # LL surfaces for user-defined pairs of paras
    #                     n_grids = [[30,30]] * 6, 
    #                     para_scales = para_scales,
    #                     n_trials = n_trials,
    #                     fit_method = 'DE', n_x0s = 8, pool = pool)
    
    # # # ----------------------- Model Comparison ----------------------------------
    # fake_data = generate_fake_data('LossCounting', ['loss_count_threshold_mean','loss_count_threshold_std'], [10,3], n_trials = 1000)
    # fake_data = generate_fake_data('RW1972_softmax', ['learn_rate_rew','softmax_temperature'], [0.2,0.3])
    # choice_history, reward_history, p_reward = generate_fake_data('Hattori2019', ['learn_rate_rew','learn_rate_unrew', 'forget_rate','softmax_temperature'], 
    #                                                   [0.23392543, 0.318161268, 0.3, 0.22028081], n_trials = 100)
    
    # model_comparison = BanditModelComparison(choice_history, reward_history, p_reward)
    # model_comparison.fit(pool = pool, plot_predictive=[1,2,3])
    # model_comparison.show()
    # model_comparison.plot()

    # choice_history, reward_history, p_reward = generate_fake_data('Hattori2019_CK', 
    #                                                   ['learn_rate_rew','learn_rate_unrew', 'forget_rate','softmax_temperature',
    #                                                     'choice_step_size','choice_softmax_temperature'], 
    #                                                   [0.23392543, 0.318161268, 0.3, 0.22028081, 0.2, 0.5], n_trials = 1000)
    # plot_session_lightweight([choice_history, reward_history, p_reward])
    
    # choice_history, reward_history, p_reward = generate_fake_data('Hattori2019_CK', 
    #                                                   ['learn_rate_rew','learn_rate_unrew', 'forget_rate','softmax_temperature',
    #                                                     'choice_step_size','choice_softmax_temperature'], 
    #                                                   [0.4, 0.2, 0.2, 0.25, 0.5, 1], n_trials = 1000)
    
    # model_comparison = BanditModelComparison(choice_history, reward_history, p_reward, models=[15, 16, 17])
    # model_comparison.fit(pool = pool, plot_predictive=[1,2,3])
    # model_comparison.show()
    # model_comparison.plot()

    # choice_history, reward_history, p_reward = generate_fake_data('IdealpHatGreedy', [],[], n_trials = 1000)  # Almost Hattori et al.
    # model_comparison = BanditModelComparison(choice_history, reward_history, p_reward, models = [
    #             # No bias (1-8)
    #             ['Hattori2019', ['learn_rate_rew', 'learn_rate_unrew', 'forget_rate', 'softmax_temperature'],[0, 0, -1, 1e-2],[1, 1, 1, 15]],
                
    #             # With bias (9-15)
    #             ['Hattori2019', ['learn_rate_rew', 'learn_rate_unrew', 'forget_rate', 'softmax_temperature', 'biasL'],[0, 0, -1, 1e-2, -5],[1, 1, 1, 15, 5]],
    #           ]
    # )
    # model_comparison.fit(pool = pool, plot_predictive=[1,2,3])  # Plot predictive traces for the 1st, 2nd, and 3rd models
    # model_comparison.plot()
    # model_comparison.show()

    # plot_model_comparison_predictive_choice_prob(model_comparison, smooth_factor = 1)

    ## ----
    choice_history, reward_history, p_reward = generate_fake_data('Hattori2019_CK', 
                             ['learn_rate_rew','learn_rate_unrew', 'forget_rate','softmax_temperature', 'biasL',
                                                       'choice_step_size','choice_softmax_temperature'], 
                             [0.23392543, 0.318161268, 0.3, 0.22028081, 0.3, 0.2, 2], n_trials = 1000)
       
    model_comparison = BanditModelComparison(choice_history, reward_history, p_reward, models= list(np.arange(9,22)))
    model_comparison.fit(pool = pool, plot_predictive=[1,2,3])
    model_comparison.show()
    model_comparison.plot()
        
    ## ----
    # choice_history, reward_history, p_reward = generate_fake_data('IdealpHatGreedy', [],[], n_trials = 1000)  # Almost Hattori et al.
    # model_comparison = BanditModelComparison(choice_history, reward_history, p_reward, models = [
    #             # No bias (1-8)
    #             ['Hattori2019', ['learn_rate_rew', 'learn_rate_unrew', 'forget_rate', 'softmax_temperature'],[0, 0, -1, 1e-2],[1, 1, 1, 15]],
                
    #             # With bias (9-15)
    #             ['Hattori2019', ['learn_rate_rew', 'learn_rate_unrew', 'forget_rate', 'softmax_temperature', 'biasL'],[0, 0, -1, 1e-2, -5],[1, 1, 1, 15, 5]],
    #           ]
    # )
    # # model_comparison.fit(pool = pool, plot_predictive=[1,2,3])  # Plot predictive traces for the 1st, 2nd, and 3rd models
    # model_comparison.cross_validate(pool = pool, k_fold = 2)
    # display(model_comparison.prediction_accuracy_CV)
    

    # # # ----------------------- Confusion Matrix ----------------------------------
    # compute_confusion_matrix(models = [2,3], n_runs = 20, n_trials = 1000, pool = pool)
    # confusion_results = pickle.load(open(".\\results\\confusion_results_1_100_1000.p", "rb"))
    # plot_confusion_matrix(confusion_results, order = [1,4,2,3,5,7,6,8])
    
    
    # =============== Bias ==================
    # n_trials = 300
    
    # forager = 'RW1972_softmax'
    # para_names = ['learn_rate_rew','softmax_temperature','biasL']
    # para_scales = ['linear','log','linear']
    # para_bounds = [[0,1e-2,-5],
    #                 [1, 15, 5]]
    
    # compute_LL_surface(forager, para_names, para_bounds, para_scales = para_scales, 
    #                     true_para = [0.2, 0.4, 2], n_trials = n_trials, para_2ds = [[0,1],[0,2],[1,2]],
    #                     fit_method = 'DE', n_x0s = 8, pool = '')
    
    # # fake_data = generate_fake_data('RW1972_softmax', ['learn_rate_rew','softmax_temperature','biasL'], 
    # #                                                   [0.2, 0.3, 2])
    # # plot_session_lightweight(fake_data)
    
    # ---------------------------------------------
    # choice_history, reward_history, p_reward = generate_fake_data('RW1972_softmax', ['learn_rate_rew','softmax_temperature'], [0.2,0.3], n_trials = 100)
    # model_comparison = BanditModelComparison(choice_history, reward_history, p_reward, models = [1,2,3])
    # model_comparison.fit(pool = pool, plot_predictive=[1,2,3]) # Plot predictive traces for the 1st, 2nd, and 3rd models
    # model_comparison.show()
    # model_comparison.plot()
    
    # --------------------------------------------
    # compute_confusion_matrix(n_runs = 50, n_trials = 500, pool = pool, save_file = 'confusion_results_2_50_500.p')
    # confusion_results = pickle.load(open("..\\results\\confusion_results_2_50_500.p", "rb"))
    # plot_confusion_matrix(confusion_results)


    # models = [
    #             # No bias (1-8)
    #             # ['LossCounting', ['loss_count_threshold_mean', 'loss_count_threshold_std'], [0,0], [40,10]],                   
    #             #　['RW1972_epsi', ['learn_rate_rew', 'epsilon'],[0, 0],[1, 1]],
    #             #　['LNP_softmax',  ['tau1', 'softmax_temperature'], [1e-3, 1e-2], [100, 15]],                 
    #             # ['LNP_softmax', ['tau1', 'tau2', 'w_tau1', 'softmax_temperature'],[1e-3, 1e-1, 0, 1e-2],[15, 40, 1, 15]],                 
    #             ['RW1972_softmax', ['learn_rate_rew', 'softmax_temperature'],[0, 1e-2],[1, 15]],
    #             # ['Hattori2019', ['learn_rate_rew', 'learn_rate_unrew', 'softmax_temperature'],[0, 0, 1e-2],[1, 1, 15]],
    #             # ['Bari2019', ['learn_rate_rew', 'forget_rate', 'softmax_temperature'],[0, 0, 1e-2],[1, 1, 15]],
    #             # ['Hattori2019', ['learn_rate_rew', 'learn_rate_unrew', 'forget_rate', 'softmax_temperature'],[0, 0, 0, 1e-2],[1, 1, 1, 15]],
                
    #             # With bias (9-16)
    #             # ['RW1972_epsi', ['learn_rate_rew', 'epsilon', 'biasL'],[0, 0, -0.5],[1, 1, 0.5]],
    #             # ['LNP_softmax',  ['tau1', 'softmax_temperature', 'biasL'], [1e-3, 1e-2, -5], [100, 15, 5]],                 
    #             # ['LNP_softmax', ['tau1', 'tau2', 'w_tau1', 'softmax_temperature', 'biasL'],[1e-3, 1e-1, 0, 1e-2, -5],[15, 40, 1, 15, 5]],                 
    #             ['RW1972_softmax', ['learn_rate_rew', 'softmax_temperature', 'biasL'],[0, 1e-2, -5],[1, 15, 5]],
    #             # ['Hattori2019', ['learn_rate_rew', 'learn_rate_unrew', 'softmax_temperature', 'biasL'],[0, 0, 1e-2, -5],[1, 1, 15, 5]],
    #             # ['Bari2019', ['learn_rate_rew', 'forget_rate', 'softmax_temperature', 'biasL'],[0, 0, 1e-2, -5],[1, 1, 15, 5]],
    #             # ['Hattori2019', ['learn_rate_rew', 'learn_rate_unrew', 'forget_rate', 'softmax_temperature', 'biasL'],[0, 0, 0, 1e-2, -5],[1, 1, 1, 15, 5]],
    #          ]
    
    # compute_confusion_matrix(models = models, n_runs = 100, n_trials = 500, pool = pool, 
    #                          save_file = 'confusion_results_4_100_1000_bias_test.p')
    
    # confusion_results = pickle.load(open("..\\results\\confusion_results_4_100_1000_bias_test.p", "rb"))
    # plot_confusion_matrix(confusion_results)
    
    #%%
    pool.close()   # Just a good practice
    pool.join()

    
    
    
    
    
    
    
    
    
    
    
    
    
    
