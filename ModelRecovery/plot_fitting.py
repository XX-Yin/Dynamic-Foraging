# -*- coding: utf-8 -*-
"""
Created on Sat Mar 21 13:47:05 2020

@author: Han
"""

import numpy as np
import matplotlib.pyplot as plt
import scipy.ndimage
from matplotlib.gridspec import GridSpec
from matplotlib.pyplot import cm

# matplotlib.use('qt5agg')
plt.rcParams.update({'font.size': 13})


def plot_para_recovery(forager, true_paras, fitted_paras, para_names, para_bounds, n_trials):
    n_paras, n_models = np.shape(fitted_paras)
    
    fig = plt.figure(figsize=((n_paras+1)*5, 5*1))
    
    fig.text(0.05,0.94,'Parameter Recovery: %s' % (forager), fontsize = 15)

    gs = GridSpec(1,n_paras+1, wspace=0.3, hspace=0.5, bottom=0.13) 
    
    colors = cm.copper((true_paras[1,:]-para_bounds[0][1]+1e-6)/(para_bounds[1][1]-para_bounds[0][1]+1e-6)) # Use std as color
    
    # 1. 1-D plot
    for pp in range(n_paras):
        fig.add_subplot(gs[0,pp])
        plt.scatter(true_paras[pp,:], fitted_paras[pp,:], marker = 'o', facecolors='none', s = 100, c = colors)
        plt.plot([para_bounds[0][pp], para_bounds[1][pp]], [para_bounds[0][pp], para_bounds[1][pp]],'k--',linewidth=1)
        
        plt.title(para_names[pp])
        plt.xlabel('True')
        plt.ylabel('Fitted')
        plt.axis('square')
        
    # 2. 2-D plot
    ax = fig.add_subplot(gs[0,pp+1])    
    for n in range(n_models):
        plt.plot(true_paras[0,n], true_paras[1,n],'ok', markersize=12, fillstyle='none', c = colors[n])
        plt.plot(fitted_paras[0,n], fitted_paras[1,n],'ok', markersize=8, c = colors[n])
        plt.plot([true_paras[0,n], fitted_paras[0,n]], [true_paras[1,n], fitted_paras[1,n]],'-', linewidth=1, c = colors[n])
        
        # Draw the fitting bounds
        x1, y1 = para_bounds[0]
        x2, y2 = para_bounds[1]
        
        plt.plot([x1,x2,x2,x1,x1],[y1,y1,y2,y2,y1],'k--',linewidth=1)
        
        plt.xlabel(para_names[0])
        plt.ylabel(para_names[1])
        ax.set_aspect(1.0/ax.get_data_ratio())  # This is the correct way of setting square display
        plt.title('n_trials = %g'%n_trials)
    
    plt.show()


def plot_LL_surface(LLs,true_para,fit_history,para_names,p1,p2):

    # ==== Plot LL surface ===
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(1, 1, 1) 
    
    # plt.pcolor(pp1, pp2, LLs, cmap='RdBu', vmin=z_min, vmax=z_max)
    
    dx = p1[1]-p1[0]
    dy = p2[1]-p2[0]
    extent=[p1.min()-dx/2, p1.max()+dx/2, p2.min()-dy/2, p2.max()+dy/2]
    plt.imshow(LLs, cmap='plasma', extent=extent, interpolation='none', origin='lower')
    plt.colorbar()
    
    plt.contour(-np.log(-LLs), colors='grey', levels = 10, extent=extent)
    
    # ==== True value ==== 
    plt.plot(true_para[0], true_para[1],'ok', markersize=17, markeredgewidth=3, fillstyle='none')
    
    # ==== Fitting history ==== 
    fit_history = np.array(fit_history)
    sizes = 100 * np.linspace(0.1,1,np.shape(fit_history)[0])
    plt.scatter(fit_history[:,0], fit_history[:,1], s = sizes, c = 'k')
    plt.plot(fit_history[:,0], fit_history[:,1], 'k:')
    
    ax.set_aspect(1.0/ax.get_data_ratio()) 
    plt.xlabel(para_names[0])
    plt.ylabel(para_names[1])
    plt.title('Log Likelihood p(data|parameter)')
    plt.show()
    