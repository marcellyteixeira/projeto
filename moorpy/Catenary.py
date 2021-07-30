

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm
#import moorpy.MoorSolve as msolve
from moorpy.helpers import CatenaryError, dsolve2



def catenary(XF, ZF, L, EA, W, CB=0, HF0=0, VF0=0, Tol=0.000001, nNodes=20, MaxIter=50, plots=0):
    '''
    The quasi-static mooring line solver. Adapted from catenary subroutine in FAST v7 by J. Jonkman.
    Note: this version is updated Oct 7 2020 to use the dsolve solver.
    
    Parameters
    ----------
    XF : float
        Horizontal distance from end 1 to end 2 [m]
    ZF : float
        Vertical distance from end 1 to end 2 [m] (positive up)
    L  : float
        Unstretched length of line [m]
    EA : float
        Extensional stiffness of line [N]
    W  : float
        Weight of line in fluid per unit length [N/m]   
    CB : float, optional
        If positive, coefficient of seabed static friction drag. If negative, no seabed contact and the value is the distance down from end A to the seabed in m\
            NOTE: friction (CV > 0) should only be applied when end A of the line is at an anchor, otherwise assumptions are violated.
    HF0 : float, optional
        Horizontal fairlead tension. If zero or not provided, a guess will be calculated.
    VF0 : float, optional
        Vertical fairlead tension. If zero or not provided, a guess will be calculated.
    
    Tol    :  float, optional
        Convergence tolerance within Newton-Raphson iteration specified as an absolute displacement error
    nNodes : int, optional
        Number of nodes to describe the line
    MaxIter:  int, optional
        Maximum number of iterations to try before resetting to default ICs and then trying again
    plots  : int, optional
        1: plot output, 0: don't
    
    
    Returns
    -------
    : tuple
        (end 1 horizontal tension, end 1 vertical tension, end 2 horizontal tension, end 2 vertical tension, info dictionary) [N] (positive up)
    
    '''

    
    # make info dict to contain any additional outputs
    info = dict(error=False)
    
    info['call'] = f"catenary({XF}, {ZF}, {L}, {EA}, {W}, CB={CB}, HF0={HF0}, VF0={VF0}, Tol={Tol}, MaxIter={MaxIter}, plots=1)"
    
    # flip line in the solver if it is buoyant
    if W < 0:
        W = -W
        ZF = -ZF
        CB = -10000.   # <<< TODO: set this to the distance to sea surface <<<
        flipFlag = True
    else:
        flipFlag = False
    
    # reverse line in the solver if end A is above end B
    if ZF < 0:    
        ZF = -ZF
        reverseFlag = True   
    else:
        reverseFlag = False
    
    # ensure the input variables are realistic
    if XF <= 0.0:
        raise CatenaryError("XF is zero or negative!")
    if L <= 0.0:
        raise CatenaryError("L is zero or negative!")
    if EA <= 0.0:
        raise CatenaryError("EA is zero or negative!")

    
    # Solve for the horizontal and vertical forces at the fairlead (HF, VF) and at the anchor (HA, VA)
    
    # There are many "ProfileTypes" of a mooring line and each must be analyzed separately (1-3 are consistent with FAST v7)
    # ProfileType=0: Entire line is on seabed
    # ProfileType=1: No portion of the line rests on the seabed
    # ProfileType=2: A portion of the line rests on the seabed and the anchor tension is nonzero
    # ProfileType=3: A portion of the line must rest on the seabed and the anchor tension is zero
    # ProfileType=4: The line is negatively buoyant, seabed interaction is enabled, and the line 
        # is longer than a full L between end points (including stretching) i.e. it is horizontal
        # along the seabed from the anchor, then vertical to the fairlaed. Computes the maximum
        # stretched length of the line with seabed interaction beyond which the line would have to 
        # double-back on itself; the line forms an "L" between the anchor and fairlead. Then it 
        # models it as bunched up on the seabed (instead of throwing an error)
    
    EA_W = EA/W
    
    # calculate what line length would be hanging it it were fully slack, vertical
    if CB < 0:  # free floating (potentially U shaped case)
        LHanging1 = np.sqrt(2.0*(  -CB)*EA_W + EA_W*EA_W) - EA_W  # unstretched hanging length at end A
        LHanging2 = np.sqrt(2.0*(ZF-CB)*EA_W + EA_W*EA_W) - EA_W  # unstretched hanging length at end B
        LHanging = LHanging1+LHanging2        
    else:       # at least one end on seabed    
        LHanging = np.sqrt(2.0*ZF*EA_W + EA_W*EA_W) - EA_W  # unstretched length of line hanging vertically to seabed    
    
    
    # calculate a vertical stiffness estimate for an end lifting off the seabed
    def dV_dZ_s(z0, H):   # height off seabed to evaluate at (infinite if 0), horizontal tension
        #return W*(z0*W/H + 1)/np.sqrt( (z0*W/H + 1)**2 - 1)   # inelastic apprxoimation
        return W # returning a fully slack line approximation, 
        #   because a large value here risks adding a bad cross coupling term in the system stiffness matrix
    

    # ProfileType 0 case - entirely along seabed
    if ZF==0.0 and CB >= 0.0 and W > 0:
    
        ProfileType = 0        
        # this is a special case that requires no iteration
        
        HF = np.max([0, (XF/L - 1.0)*EA])   # calculate fairlead tension based purely on elasticity
        VF = 0.0
        HA = np.max([0.0, HF - CB*W*L])     # calculate anchor tension by subtracting any seabed friction
        VA = 0.0
        
        if HF > 0: # if taut
            dHF_dXF = EA/L    # approximation <<<  what about friction?  <<<<<<<<
            #dVF_dZF = W + HF/L # vertical stiffness <<< approximation a
            dVF_dZF = dV_dZ_s(Tol*L, HF)      # vertical stiffness <<< approximation b
        else:  # if slack
            dHF_dXF = 0.0
            dVF_dZF = W  # vertical stiffness 
        
        
        info["HF"] = HF     # solution to be used to start next call (these are the solved variables, may be for anchor if line is reversed)
        info["VF"] = 0.0
        info["stiffnessB"]  = np.array([[dHF_dXF, 0.0], [0.0, dVF_dZF]])
        info["stiffnessA"]  = np.array([[dHF_dXF, 0.0], [0.0, dVF_dZF]])
        info["LBot"] = L
        info['ProfileType'] = 0
        info['Zextreme'] = 0
    
    
    # ProfileType 4 case - fully slack
    elif (W > 0.0) and (L >= XF + LHanging):
        
        if CB >= 0.0:
            ProfileType = 4        
            # this is a special case that requires no iteration
            
            HF = 0.0
            VF = W*LHanging
            HA = 0.0
            VA = 0.0
            
            dVF_dZF = W / np.sqrt(2.0*ZF/EA_W + 1.0)  # vertical stiffness
            
            info["HF"] = HF     # solution to be used to start next call (these are the solved variables, may be for anchor if line is reversed)
            info["VF"] = VF
            info["stiffnessB"]  = np.array([[0.0, 0.0], [0.0, dVF_dZF]])
            info["stiffnessA"]  = np.array([[0.0, 0.0], [0.0, W]]) 
            info["LBot"] = L - LHanging
            info['ProfileType'] = 4
            info['Zextreme'] = 0
    
        else:  # U shaped
            ProfileType = 5   
    
            HF = 0.0
            VF = W*LHanging1
            HA = 0.0
            VA = W*LHanging2
            
            dVF_dZF = W / np.sqrt(2.0*ZF/EA_W + 1.0)  # vertical stiffness
            
            info["HF"] = HF     # solution to be used to start next call (these are the solved variables, may be for anchor if line is reversed)
            info["VF"] = VF
            info["stiffnessB"]  = np.array([[0.0, 0.0], [0.0, W / np.sqrt(2.0*(ZF-CB)/EA_W + 1.0)]])
            info["stiffnessA"]  = np.array([[0.0, 0.0], [0.0, W / np.sqrt(2.0*(  -CB)/EA_W + 1.0)]])
            info["LBot"] = L - LHanging
            info['ProfileType'] = 5
            info['Zextreme'] = CB
    
        
    # Use an iterable solver function to solve for the forces on the line
    else: 

        # Initialize some commonly used terms that don't depend on the iteration:

        WL =  W *L
        WEA     =  W *EA
        L_EA  =  L /EA
        CB_EA =  CB/EA
        #MaxIter = 50 #int(1.0/Tol)   # Smaller tolerances may take more iterations, so choose a maximum inversely proportional to the tolerance

        # more initialization
        I         = 1                 # Initialize iteration counter        
        FirstIter = 1                 # 1 means first attempt (can be retried), 0 means it's alread been retried, -1 triggers a retry


        # make HF and VF initial guesses if either was provided as zero <<<<<<<<<<<< why does it matter if VF0 is zero??
        if HF0 <= 0 or VF0 <= 0:

            XF2 = XF*XF;
            ZF2 = ZF*ZF;

            if ( L <= np.sqrt( XF2 + ZF2 ) ): # if the current mooring line is taut
                Lamda0 = 0.2
            else:                             # The current mooring line must be slack and not vertical
                Lamda0 = np.sqrt( 3.0*( ( L*L - ZF2 )/XF2 - 1.0 ) )
                
            HF = np.max([ abs( 0.5*W* XF/ Lamda0 ), Tol ]); # ! As above, set the lower limit of the guess value of HF to the tolerance
            VF = 0.5*W*( ZF/np.tanh(Lamda0) + L )
        else:
            HF = 1.0*HF0
            VF = 1.0*VF0

        # >>> note, the above Tol uses should be adjusted now that I've changed it to be absolute and distance <<<

        # make sure required values are non-zero
        HF = np.max([ HF, Tol ])
        XF = np.max([ XF, Tol ])
        ZF = np.max([ ZF, Tol ])

        # some initial values just for printing before they're filled in
        EXF=0
        EZF=0

        # Solve the analytical, static equilibrium equations for a catenary (or taut) mooring line with seabed interaction:
        X0 = [HF, VF]
        Ytarget = [0,0]
        args = dict(cat=[XF, ZF, L, EA, W, CB, WL, WEA, L_EA, CB_EA], step=[0.15,1.0,1.5])  
        # call the master solver function
        #X, Y, info2 = msolve.dsolve(eval_func_cat, X0, Ytarget=Ytarget, step_func=step_func_cat, args=args, tol=Tol, maxIter=MaxIter, a_max=1.2)
        X, Y, info2 = dsolve2(eval_func_cat, X0, Ytarget=Ytarget, step_func=step_func_cat, args=args, 
                              ytol=Tol, stepfac=1, maxIter=MaxIter, a_max=1.2)
        
      
        # retry if it failed        
        if  info2['iter'] >= MaxIter-1  or  info2['oths']['error']==True or np.linalg.norm(info2['err']) > 10*Tol:
            #  ! Perhaps we failed to converge because our initial guess was too far off.
            #   (This could happen, for example, while linearizing a model via large
            #   pertubations in the DOFs.)  Instead, use starting values documented in:
            #   Peyrot, Alain H. and Goulois, A. M., "Analysis Of Cable Structures,"
            #   Computers & Structures, Vol. 10, 1979, pp. 805-813:
            # NOTE: We don't need to check if the current mooring line is exactly
            #       vertical (i.e., we don't need to check if XF == 0.0), because XF is
            #       limited by the tolerance above. */
            
            XF2 = XF*XF;
            ZF2 = ZF*ZF;

            if ( L <= np.sqrt( XF2 + ZF2 ) ): # if the current mooring line is taut
                Lamda0 = 0.2
            else:                             # The current mooring line must be slack and not vertical
                Lamda0 = np.sqrt( 3.0*( ( L*L - ZF2 )/XF2 - 1.0 ) )
                
            HF = np.max([ abs( 0.5*W* XF/ Lamda0 ), Tol ])     # As above, set the lower limit of the guess value of HF to the tolerance
            VF = 0.5*W*( ZF/np.tanh(Lamda0) + L )
        
            X0 = [HF, VF]
            Ytarget = [0,0]
            args = dict(cat=[XF, ZF, L, EA, W, CB, WL, WEA, L_EA, CB_EA], step=[0.1,0.8,1.5])   # step: alpha_min, alpha0, alphaR
            # call the master solver function
            #X, Y, info3 = msolve.dsolve(eval_func_cat, X0, Ytarget=Ytarget, step_func=step_func_cat, args=args, tol=Tol, maxIter=MaxIter, a_max=1.1) #, dX_last=info2['dX'])
            X, Y, info3 = dsolve2(eval_func_cat, X0, Ytarget=Ytarget, step_func=step_func_cat, args=args, 
                                  ytol=Tol, stepfac=1, maxIter=MaxIter, a_max=1.2)
                
            # retry if it failed              
            if  info3['iter'] >= MaxIter-1  or  info3['oths']['error']==True:
            
                X0 = X
                Ytarget = [0,0]
                args = dict(cat=[XF, ZF, L, EA, W, CB, WL, WEA, L_EA, CB_EA], step=[0.1,1.0,2.0])  
                # call the master solver function
                #X, Y, info4 = msolve.dsolve(eval_func_cat, X0, Ytarget=Ytarget, step_func=step_func_cat, args=args, tol=Tol, maxIter=10*MaxIter, a_max=1.15) #, dX_last=info3['dX'])
                X, Y, info4 = dsolve2(eval_func_cat, X0, Ytarget=Ytarget, step_func=step_func_cat, args=args, 
                                      ytol=Tol, stepfac=1, maxIter=MaxIter, a_max=1.2)
                    
                # check if it failed                  
                if  info4['iter'] >= 10*MaxIter-1  or  info4['oths']['error']==True:
                                    
                    print("catenary solve failed on all 3 attempts.")
                    print(f"catenary({XF}, {ZF}, {L}, {EA}, {W}, CB={CB}, HF0={HF0}, VF0={VF0}, Tol={Tol}, MaxIter={MaxIter}, plots=1)")
                    
                    print("First attempt's iterations are as follows:")
                    for i in range(info2['iter']+1):
                        print(f" Iteration {i}: HF={info2['Xs'][i,0]: 8.4e}, VF={info2['Xs'][i,1]: 8.4e}, EX={info2['Es'][i,0]: 6.2e}, EZ={info2['Es'][i,1]: 6.2e}")
                    
                    print("Second attempt's iterations are as follows:")
                    for i in range(info3['iter']+1):
                        print(f" Iteration {i}: HF={info3['Xs'][i,0]: 8.4e}, VF={info3['Xs'][i,1]: 8.4e}, EX={info3['Es'][i,0]: 6.2e}, EZ={info3['Es'][i,1]: 6.2e}")
                                    
                    
                    print("Last attempt's iterations are as follows:")
                    for i in range(info4['iter']+1):
                        print(f" Iteration {i}: HF={info4['Xs'][i,0]: 8.4e}, VF={info4['Xs'][i,1]: 8.4e}, EX={info4['Es'][i,0]: 6.2e}, EZ={info4['Es'][i,1]: 6.2e}")
                                

                    '''
                    # plot solve performance
                    fig, ax = plt.subplots(4,1, sharex=True)
                    ax[0].plot(np.hstack([info2['Xs'][:,0], info3['Xs'][:,0], info4['Xs'][:,0]]))
                    ax[1].plot(np.hstack([info2['Xs'][:,1], info3['Xs'][:,1], info4['Xs'][:,1]]))
                    ax[2].plot(np.hstack([info2['Es'][:,0], info3['Es'][:,0], info4['Es'][:,0]]))
                    ax[3].plot(np.hstack([info2['Es'][:,1], info3['Es'][:,1], info4['Es'][:,1]]))
                    ax[0].set_ylabel("HF")
                    ax[1].set_ylabel("VF")
                    ax[2].set_ylabel("X err")
                    ax[3].set_ylabel("Z err")
                                    
                    # plot solve path
                    plt.figure()
                    
                    #c = np.hypot(info2['Es'][:,0], info2['Es'][:,1])
                    
                    
                    c = np.arange(info2['iter']+1)
                    c = cm.jet((c-np.min(c))/(np.max(c)-np.min(c)))
                    
                    for i in np.arange(info2['iter']):
                        plt.plot(info2['Xs'][i:i+2,0], info2['Xs'][i:i+2,1],":", c=c[i])
                    plt.plot(info2['Xs'][0,0], info2['Xs'][0,1],"o")
                    
                    c = np.arange(info3['iter']+1)
                    c = cm.jet((c-np.min(c))/(np.max(c)-np.min(c)))
                    
                    for i in np.arange(info3['iter']):
                        plt.plot(info3['Xs'][i:i+2,0], info3['Xs'][i:i+2,1], c=c[i])
                    plt.plot(info3['Xs'][0,0], info3['Xs'][0,1],"*")
                    
                    c = np.arange(info4['iter']+1)
                    c = cm.jet((c-np.min(c))/(np.max(c)-np.min(c)))
                    
                    for i in np.arange(info4['iter']):
                        plt.plot(info4['Xs'][i:i+2,0], info4['Xs'][i:i+2,1], c=c[i])
                    plt.plot(info4['Xs'][0,0], info4['Xs'][0,1],"*")
                   
                    plt.title("catenary solve path for troubleshooting")
                    plt.show()
                
                    #breakpoint()
                    '''
                    raise CatenaryError("catenary solver failed.")
                
                else:                            # if the solve was successful,
                    info.update(info4['oths'])   # copy info from last solve into existing info dictionary
                    info['catenary'] = info4
                    
            else:                            # if the solve was successful,
                info.update(info3['oths'])   # copy info from last solve into existing info dictionary
                info['catenary'] = info3    
        else:                            # if the solve was successful,
            info.update(info2['oths'])   # copy info from last solve into existing info dictionary
            info['catenary'] = info2
        
        # check for errors ( WOULD SOME NOT ALREADY HAVE BEEN CAUGHT AND RAISED ALREADY?)
        if info['error']==True:
            #breakpoint()
            # >>>> what about errors for which we can first plot the line profile?? <<<<
            raise CatenaryError("Error in catenary computations: "+info['message'])

        #if info['Zextreme'] < CB:
        #    info["warning"] = "Line is suspended from both ends but hits the seabed (this isn't allowed in MoorPy)"
    
        ProfileType = info['ProfileType']
        HF = X[0]
        VF = X[1]
        HA = info['HA']
        VA = info['VA']
        
        
    # compute the Zextreme value - for a freely suspended line, if necessary, check to ensure the line doesn't droop and hit the seabed
    if info['ProfileType']==1 and CB < 0 and  VF-WL < 0.0:   # only need to do this if the line is slack (has zero slope somewhere)

        VFMinWL            = VF - WL;
        LBot               = L  - VF/W;    # unstretched length of line resting on seabed (Jonkman's PhD eqn 2-38), LMinVFOVrW
        HF_W             =      HF/W;
        HF_WEA           =      HF/WEA
        VF_WEA           =      VF/WEA
        VF_HF            =      VF/HF
        VFMinWL_HF       = VFMinWL/HF
        VF_HF2           = VF_HF     *VF_HF
        VFMinWL_HF2      = VFMinWL_HF*VFMinWL_HF
        SQRT1VF_HF2      = np.sqrt( 1.0 + VF_HF2      )
        SQRT1VFMinWL_HF2 = np.sqrt( 1.0 + VFMinWL_HF2 )
        
        # this is indicated by the anchor force having a positive value, meaning it's helping hold up the line
        info["Sextreme"] = L-VF/W  # arc length where slope is zero
        info["Zextreme"] = (1 - SQRT1VFMinWL_HF2)*HF_W - 0.5* VFMinWL**2/WEA  # max or min line elevation (where slope=0)
        info["Xextreme"] = ( -np.log(VFMinWL_HF + SQRT1VFMinWL_HF2))*HF_W + HF*info["Sextreme"]/EA
    else:
        info["Sextreme"] = 0.0
        info["Zextreme"] = 0.0
        info["Xextreme"] = 0.0    
        
        
    # handle special case of a U-shaped line that has seabed contact (using 2 new catenary solves)
    if info['ProfileType']==1 and info["Zextreme"] < CB:
    
        # we will solve this as two separate lines to form the U shape
        info['ProfileType'] = 'U'
        
        X1_0 = info['Xextreme']   # define fake anchor point as lowest point of line (if the seabed wasn't there)
        X2_0 = XF - X1_0
        L1 = info['Sextreme']
        L2 = L-L1
        Z1 = CB     # height from seabed to original 'anchor' end
        Z2 = -Z1 + ZF  # height from seabed to fairlead end 
        
        # set up a 1D solve for the correct choice of the anchor point so that horizontal tensions balance
        
        def eval_func_U(X, args):
        
            info = dict(error=False)
            
            X1 = X[0]
            X2 = XF-X1
            
            # note: reducing tolerances for these sub-calls <<< how much is good? <<<
            (fAH1, fAV1, fBH1, fBV1, info1) = catenary(X1, Z1, L1, EA, W, CB=0, Tol=0.5*Tol, MaxIter=MaxIter)
            (fAH2, fAV2, fBH2, fBV2, info2) = catenary(X2, Z2, L2, EA, W, CB=0, Tol=0.5*Tol, MaxIter=MaxIter)
            
            Himbalance = fBH2 - fBH1
            
            K1 = info1["stiffnessB"]
            K2 = info2["stiffnessB"]
            
            info['dH_dX'] = K1[0,0] + K2[0,0]  # horizontal stiffness on connection point on seabed between two line portions
            
            #print(f" X1 = {X1}, H1 = {fBH1}, H2 = {fBH2}, err={Himbalance}, dH/dX = {info['dH_dX']}")\
            #breakpoint()
        
            return np.array([Himbalance]), info, False      # returns Y value, misc dict, and stop flag
            
        
        def step_func_U(X, args, Y, info, Ytarget, err, tols, iter, maxIter):
            
            dX = - err[0] / info['dH_dX']   
            
            #print(f" Step is {dX}")
            
            return np.array([dX])                              # returns dX (step to make)


        # call this to solve for line shapes that balance the horizontal tension in the line
        X, Y, infoU = dsolve2(eval_func_U, [X1_0], step_func=step_func_U, ytol=0.25*Tol, stepfac=1, maxIter=20, a_max=1.2, display=0)
        X1 = X[0]
        X2 = XF-X1
        
        # call one more time to get final values
        (fAH1, fAV1, fBH1, fBV1, info1) = catenary(X1, Z1, L1, EA, W, CB=0, Tol=0.5*Tol, MaxIter=MaxIter, plots=plots)
        (fAH2, fAV2, fBH2, fBV2, info2) = catenary(X2, Z2, L2, EA, W, CB=0, Tol=0.5*Tol, MaxIter=MaxIter, plots=plots)

        if plots > 0 or (info1['error'] and info2['error']):
        
            info['X' ] = np.hstack([ info1["X" ] , info2["X" ]+X1 ])
            info['Z' ] = np.hstack([ info1["Z" ] , info2["Z" ]+Z1 ])
            info['s' ] = np.hstack([ info1["s" ] , info2["s" ]+L1 ])
            info['Te'] = np.hstack([ info1["Te"] , info2["Te"]    ])
            
            # re-reverse line distributed data back to normal if applicable
            if reverseFlag:  
                info['s']  =  L - info['s' ][::-1]
                info['X']  = XF - info['X' ][::-1]
                info['Z']  =      info['Z' ][::-1] - ZF  # remember ZF still has a flipped sign right now
                info['Te'] =      info['Te'][::-1]
        if flipFlag:
            raise Exception("flipFlag connot be True for the case of a U shaped line with seabed contact. Something must be wrong.")
                        
            
        
        # get stiffnesses    (check sign of A!)
        K1 = info1['stiffnessB']
        K2 = info2['stiffnessB']        
        dH_dX = 1./(1./K1[0,0] + 1./K2[0,0])
        Kmid = infoU['oths']['dH_dX']
        
        info['stiffnessA'] = np.array([[ dH_dX, K1[0,1] - K1[0,1]/Kmid*K1[0,0]], 
                                               [K1[1,0] - K1[0,0]/Kmid*K1[1,0] , K1[1,1] - K1[0,1]/Kmid*K1[1,0]]])
        
        info['stiffnessB'] = np.array([[ dH_dX, K2[0,1] - K2[0,1]/Kmid*K2[0,0]], 
                                               [K2[1,0] - K2[0,0]/Kmid*K2[1,0] , K2[1,1] - K2[0,1]/Kmid*K2[1,0]]])
                                               
        info['LBot'] = info1['LBot'] + info2['LBot']
        # not very useful outputs for this case:
        info["Sextreme"] = L1 - info1['LBot']
        info["Zextreme"] = CB
        info["Xextreme"] = X1 - info1['LBot']  
                    
        #FxA = fAH1
        #FzA = fAV1
        #FxB = fBH2
        #FzB = fBV2
        HA =  fAH1
        VA =  fAV1
        HF = -fBH2
        VF = -fBV2
        
        if plots > 3:
            plt.plot(info['X'], info['Z'])
            plt.show()

    # the normal case
    else:

        # do plotting-related calculations if needed (plots=1: show plots; plots=2: just return values)
        if plots > 0 or info['error']==True:
        
            # some arrays only used for plotting each node
            s = np.linspace(0,L,nNodes)   #  Unstretched arc distance along line from anchor to each node where the line position and tension can be output (meters)
            X = np.zeros(nNodes)          #  Horizontal locations of each line node relative to the anchor (meters)
            Z = np.zeros(nNodes)          #  Vertical   locations of each line node relative to the anchor (meters)
            Te= np.zeros(nNodes)          #  Effective line tensions at each node (N)

        
            # fully along seabed
            if ProfileType==0:
                for I in range(nNodes):
                
                    if (L-s[I])*CB*W > HF:  # if this node is in the zero tension range
                    
                        X [I] = s[I];
                        Z [I] = 0.0;
                        Te[I] = 0.0;
                    
                    else:                    # this node rests on the seabed and the tension is nonzero
                        
                        if L*CB*W > HF:  # zero anchor tension case
                            X [I] = s[I] - 1.0/EA*( HF*(s[I]-L) - CB*W*( L*s[I] - 0.5*s[I]*s[I] - 0.5*L*L ) + 0.5*HF*HF/(CB*W) )                    
                        else:
                            X [I] = s[I] + s[I]/EA*( HF - CB*W*(L-0.5*s[I]))
                        
                        Z [I] = 0.0;
                        Te[I] = HF - CB*W*(L-s[I])


            # Freely hanging line with no horizontal tension
            elif ProfileType==4:       
                for I in range(nNodes):
                    if s[I] > L-LHanging:   # this node is on the suspended/hanging portion of the line
                    
                        X [I] = XF
                        Z [I] = ZF - ( L-s[I] + 0.5*W/EA*(L-s[I])**2 )
                        Te[I] = W*(L-s[I])
                        
                    else:                   # this node is on the seabed
                        
                        X [I] = np.min([s[I], XF])
                        Z [I] = 0.0
                        Te[I] = 0.0


            # the other profile types are more involved
            else:                         
                
                # calculate some commonly used terms that depend on HF and VF:  AGAIN
                VFMinWL            = VF - WL;
                LBot               = L  - VF/W;    # unstretched length of line resting on seabed (Jonkman's PhD eqn 2-38), LMinVFOVrW
                HF_W             =      HF/W;
                #HF_WEA           =      HF/WEA
                #VF_WEA           =      VF/WEA
                VF_HF            =      VF/HF
                VFMinWL_HF       = VFMinWL/HF
                VF_HF2           = VF_HF     *VF_HF
                #VFMinWL_HF2      = VFMinWL_HF*VFMinWL_HF
                #SQRT1VF_HF2      = np.sqrt( 1.0 + VF_HF2      )
                SQRT1VFMinWL_HF2 = np.sqrt( 1.0 + VFMinWL_HF**2 )
                
                for I in range(nNodes):
                    
                    # calculate some values for the current node
                    Ws                = W       *s[I]
                    VFMinWLs          = VFMinWL + Ws   # = VF - W*(L-s[I])
                    VFMinWLs_HF       = VFMinWLs/HF    
                    s_EA              = s[I]    /EA    
                    SQRT1VFMinWLs_HF2 = np.sqrt( 1.0 + VFMinWLs_HF*VFMinWLs_HF )
                                   
                                   
                    # No portion of the line rests on the seabed
                    if ProfileType==1: 
                    
                        X [I] = ( np.log( VFMinWLs_HF + SQRT1VFMinWLs_HF2 ) - np.log( VFMinWL_HF + SQRT1VFMinWL_HF2 ) )*HF_W + s_EA* HF;
                        Z [I] = ( SQRT1VFMinWLs_HF2 - SQRT1VFMinWL_HF2 )*HF_W + s_EA*( VFMinWL + 0.5*Ws );
                        Te[I] = np.sqrt( HF*HF + VFMinWLs*VFMinWLs );
                 
                    # A portion of the line must rest on the seabed and the anchor tension is zero
                    elif ProfileType in [2,3]:             
                            
                        if CB > 0:
                            xB = LBot - HF_W/CB      # location of point at which line tension reaches zero
                        else:
                            xB = 0.0
                        xBlim = max(xB, 0.0) 
                            
                        if  s[I] <= xB:  # (aka Lbot - s > HF/(CB*W) ) if this node rests on the seabed and the tension is zero
                        
                            X [I] = s[I];
                            Z [I] = 0.0;
                            Te[I] = 0.0;
                        
                        elif( s[I] <= LBot ): # // .TRUE. if this node rests on the seabed and the tension is nonzero
                                             
                            X [I] = s[I] + 0.5*CB*W/EA * (s[I]*s[I] - 2.0*xB*s[I] + xB*xBlim)
                            Z [I] = 0.0;
                            Te[I] = HF + CB*VFMinWLs;
                        
                        else:  #  // LBot < s <= L ! This node must be above the seabed
                        
                            X [I] = LBot + HF_W*np.log( VFMinWLs_HF + SQRT1VFMinWLs_HF2 ) + HF*s_EA + 0.5*CB*W/EA *(-LBot*LBot + xB*xBlim);
                            Z [I] = ( -1.0  + SQRT1VFMinWLs_HF2)*HF_W + s_EA*(VFMinWL + 0.5*Ws ) + 0.5*   VFMinWL*VFMinWL/WEA;
                            Te[I] = np.sqrt( HF*HF + VFMinWLs*VFMinWLs );
                    
                
            # re-reverse line distributed data back to normal if applicable
            if reverseFlag:  
                s =  L - s [::-1]
                X = XF - X[::-1]
                Z = Z[::-1] - ZF  # remember ZF still has a flipped sign right now
                Te= Te[::-1]
            if flipFlag:
                Z = -Z       # flip calculated line Z coordinates (hopefully this is right)
                        

            if plots==2 or info['error']==True: # also show the profile plot

                plt.figure()
                plt.plot(X,Z)
                
            # save data to info dict
            info["X" ] = X
            info["Z" ] = Z
            info["s" ] = s
            info["Te"] = Te                                
        

    # from fairlead (upper) end stiffness matrix, get lower end stiffness matrix
    if ProfileType == 1:
        info['stiffnessA'] = info['stiffnessB']
        
    elif ProfileType in [2,3]:
        if CB == 0.0:
            info['stiffnessA'] = np.array([[info['stiffnessB'][0,0], 0], [0, dV_dZ_s(Tol, HF)]])  # vertical term is very approximate 
        else:
            info['stiffnessA'] = np.ones([2,2]) * np.nan  # if friction, flag to ensure users don't use this
    
    # un-swap line ends if they've been previously swapped, and apply global sign convention 
    # (vertical force positive-up, horizontal force positive from A to B)
    if reverseFlag:  
        ZF = -ZF  # put height rise from end A to B back to negative
        
        FxA =  HF
        FzA = -VF      # VF is positive-down convention so flip sign
        FxB = -HA
        FzB =  VA
        
        info["stiffnessA"], info["stiffnessB"] = info["stiffnessB"], info["stiffnessA"]  # swap A and B
        
        info["stiffnessA"][0,1] = -info["stiffnessA"][0,1]  # reverse off-diagonal signs
        info["stiffnessA"][1,0] = -info["stiffnessA"][1,0]
        info["stiffnessB"][0,1] = -info["stiffnessB"][0,1]
        info["stiffnessB"][1,0] = -info["stiffnessB"][1,0]
        
    else:
        FxA =  HA
        FzA =  VA
        FxB = -HF
        FzB = -VF

    if flipFlag:
        W = -W       # restore original
        ZF = -ZF     # restore original
        
        FzA = -FzA
        FzB = -FzB
        
        info["stiffnessA"], info["stiffnessB"] = info["stiffnessB"], info["stiffnessA"]  # swap A and B
        
        info["stiffnessA"][0,1] = -info["stiffnessA"][0,1]  # reverse off-diagonal signs
        info["stiffnessA"][1,0] = -info["stiffnessA"][1,0]
        info["stiffnessB"][0,1] = -info["stiffnessB"][0,1]
        info["stiffnessB"][1,0] = -info["stiffnessB"][1,0]
        
        # TODO <<< should add more info <<<

        

    # return horizontal and vertical (positive-up) tension components at each end, and length along seabed
    return (FxA, FzA, FxB, FzB, info) 




def eval_func_cat(X, args):  
    '''returns target outputs and also secondary outputs for constraint checks etc.'''
    
    info = dict(error=False)                                 # a dict of extra outputs to be returned
    
    ## Step 1. break out design variables and arguments into nice names
    HF = X[0]
    VF = X[1]
    
    [XF, ZF, L, EA, W, CB, WL, WEA, L_EA, CB_EA] = args['cat']
     
    ## Step 2. do the evaluation (this may change mutable things in args)

    #print("catenary iteration HF={:8.4e}, VF={:8.4e}".format(HF,VF))

    # calculate some commonly used terms that depend on HF and VF:

    VFMinWL            = VF - WL;      # = VA, the vertical anchor load (positive-up, but VF is positive-down)
    LBot               = L  - VF/W;    # unstretched length of line resting on seabed (Jonkman's PhD eqn 2-38), LMinVFOVrW
    HF_W             =      HF/W;
    HF_WEA           =      HF/WEA
    VF_WEA           =      VF/WEA
    VF_HF            =      VF/HF
    #VF_HF            =      np.abs(VF/HF)  # I added the abs <<<<<< <<<<<<<<<<<<<<<<<<<<<<<<<<<
    VFMinWL_HF       = VFMinWL/HF
    VF_HF2           = VF_HF     *VF_HF
    VFMinWL_HF2      = VFMinWL_HF*VFMinWL_HF
    SQRT1VF_HF2      = np.sqrt( 1.0 + VF_HF2      )
    SQRT1VFMinWL_HF2 = np.sqrt( 1.0 + VFMinWL_HF2 )
    


    # determine line profile type
    if(( CB < 0.0) or ( W  <  0.0) or ( VFMinWL >  0.0 ) ): # no portion of the line rests on the seabed
        ProfileType = 1
    elif( -CB*VFMinWL < HF ):          # a portion of the line rests on the seabed and the anchor tension is nonzero
        ProfileType = 2
    else:   # must be 0.0 < HF <= -CB*VFMinWL, meaning a portion of the line must rest on the seabed and the anchor tension is zero
        ProfileType = 3
        
   
    # Compute the error functions (to be zeroed) and the Jacobian matrix
    #   (these depend on the anticipated configuration of the mooring line):   
    
    # <<< could eliminate frequent division by W below, (make 1/W variable) >>>>>
    
    # No portion of the line rests on the seabed
    if ProfileType==1: 
        
        if (VF_HF + SQRT1VF_HF2 <= 0): 
            info['error'] = True
            info['message'] = "ProfileType 1: VF_HF + SQRT1VF_HF2 <= 0"
        elif (VFMinWL_HF + SQRT1VFMinWL_HF2 <= 0): 
            info['error'] = True
            info['message'] = "ProfileType 1: VFMinWL_HF + SQRT1VFMinWL_HF2 <= 0"
            # note: these errors seemed to occur when a buoyant line got to an HF=0 iteration (hopefully avoided now)

        else:
        
            LBot = 0  # note that there is no seabed contact (for clarity in outputs)

            EXF = ( np.log( VF_HF + SQRT1VF_HF2 ) - np.log( VFMinWL_HF + SQRT1VFMinWL_HF2 ) )*HF_W + L_EA* HF - XF  # error in horizontal distance
            
            EZF = ( SQRT1VF_HF2 - SQRT1VFMinWL_HF2 )*HF_W + L_EA*( VF - 0.5*WL ) - ZF                               # error in vertical distance
            
            dXFdHF = ((   np.log( VF_HF + SQRT1VF_HF2 ) - np.log( VFMinWL_HF + SQRT1VFMinWL_HF2 ) )/ W - 
                ( ( VF_HF + VF_HF2 /SQRT1VF_HF2 )/( VF_HF + SQRT1VF_HF2 ) 
                - ( VFMinWL_HF + VFMinWL_HF2/SQRT1VFMinWL_HF2 )/( VFMinWL_HF + SQRT1VFMinWL_HF2 ) )/ W + L_EA)
                
            dXFdVF = (( ( 1.0 + VF_HF /SQRT1VF_HF2 )/( VF_HF + SQRT1VF_HF2 ) 
                        - ( 1.0 + VFMinWL_HF /SQRT1VFMinWL_HF2 )/( VFMinWL_HF + SQRT1VFMinWL_HF2 ) )/ W)
            
            dZFdHF = ( SQRT1VF_HF2 - SQRT1VFMinWL_HF2 )/ W - ( VF_HF2 /SQRT1VF_HF2 - VFMinWL_HF2/SQRT1VFMinWL_HF2 )/ W;
            
            dZFdVF = ( VF_HF /SQRT1VF_HF2 - VFMinWL_HF /SQRT1VFMinWL_HF2 )/ W + L_EA
            #dZFdVF = ( np.sign(VF)*VF_HF /SQRT1VF_HF2 - VFMinWL_HF /SQRT1VFMinWL_HF2 )/ W + L_EA

    # A portion of the line must rest on the seabed and the anchor tension is zero
    elif ProfileType in [2, 3]:  
        
        if (VF_HF + SQRT1VF_HF2 <= 0):
            info['error'] = True
            info['message'] = "ProfileType 2 or 3: VF_HF + SQRT1VF_HF2 <= 0"
            
        else:
        
            if CB > 0:
                xB = LBot - HF_W/CB      # location of point at which line tension reaches zero
            else:
                xB = 0.0
            xBlim = max(xB, 0.0)
                    
            EXF = np.log( VF_HF + SQRT1VF_HF2 ) *HF_W - 0.5*CB_EA*W*( LBot*LBot - xBlim*xBlim ) + L_EA* HF + LBot - XF
            
            EZF = ( SQRT1VF_HF2 - 1.0 )*HF_W + 0.5*VF*VF_WEA - ZF
            
            dXFdHF = np.log( VF_HF + SQRT1VF_HF2 ) / W - ( ( VF_HF + VF_HF2 /SQRT1VF_HF2 )/( VF_HF + SQRT1VF_HF2 ) )/ W + L_EA - xBlim/EA
            
            dXFdVF = ( ( 1.0 + VF_HF /SQRT1VF_HF2 )/( VF_HF + SQRT1VF_HF2 ) )/ W + HF_WEA +xBlim*CB/EA- 1.0/W
            
            dZFdHF = ( SQRT1VF_HF2 - 1.0 - VF_HF2 /SQRT1VF_HF2 )/ W
            
            dZFdVF = ( VF_HF /SQRT1VF_HF2 )/ W + VF_WEA

    # Now compute the tensions at the anchor

    
    if ProfileType==1:          # No portion of the line rests on the seabed
        HA = HF;
        VA = VFMinWL             # note: VF is defined positive when tension pulls downward, while VA is defined positive when tension pulls up
        
    elif ProfileType==2:        # A portion of the line rests on the seabed and the anchor tension is nonzero
        HA = HF + CB*VFMinWL    # note: -VFMinWL = -(VF-W*L) is the negative of line weight NOT supported by the fairlead; i.e. the weight on the seabed
        VA = 0.0
        
    elif ProfileType==3:        # A portion of the line must rest on the seabed and the anchor tension is zero
        HA = 0.0
        VA = 0.0
        

    # if there was an error, send the stop signal
    if info['error']==True:
        #breakpoint()
        return np.zeros(2), info, True
        

    ## Step 3. group the outputs into objective function value and others
    Y = np.array([EXF, EZF])               # objective function
    
    # info is a dict of other outputs to be returned
    info["HF"] = HF     # solution to be used to start next call (these are the solved variables, may be for anchor if line is reversed)
    info["VF"] = VF
    #info["jacobian"]  = np.array([[dXFdHF, dXFdVF], [dZFdHF, dZFdVF]])
    info["stiffnessB"]  = np.linalg.inv(np.array([[dXFdHF, dXFdVF], [dZFdHF, dZFdVF]]))  # stiffness matrix at fairlead end
    info["LBot"] = LBot
    info["HA"] = HA
    info["VA"] = VA
    info["ProfileType"] = ProfileType
        
    #print("EX={:5.2e}, EZ={:5.2e}".format(EXF, EZF))
        
    return Y, info, False






def step_func_cat(X, args, Y, info, Ytarget, err, tols, iter, maxIter):
    '''General stepping functions, which can also contain special condition checks or other adjustments to the process
    
        info - the info dict created by the main catenary function
    
    '''
    [XF, ZF, L, EA, W, CB, WL, WEA, L_EA, CB_EA] = args['cat']
    
    #if abs( err[1] + ZF ) < 0.0001:
    #    breakpoint()
    
    
        
    [alpha_min, alpha0, alphaR] = args['step']  # get minimum alpha, initial alpha, and alpha reduction rate from passed arguments 
        
    #J = info['jacobian']
    #dX = -np.matmul(np.linalg.inv(J), err)   
    dX = -np.matmul(info['stiffnessB'], err)   

    
    # ! Reduce dHF by factor (between 1 at I = 1 and 0 at I = MaxIter) that reduces linearly with iteration count 
    # to ensure that we converge on a solution even in the case were we obtain a nonconvergent cycle about the 
    # correct solution (this happens, for example, if we jump to quickly between a taut and slack catenary)

    alpha = np.max([alpha_min, alpha0*(1.0 - alphaR*iter/maxIter)])
    
    #exponential approach       alpha = alpha0 * np.exp( iter/maxIter * np.log(alpha_min/alpha0 ) )

    dX[0] = dX[0]*alpha #dHF*( 1.0 - Tol*I )           
    dX[1] = dX[1]*alpha #dVF*( 1.0 - Tol*I )
    
    # To avoid an ill-conditioned situation, make sure HF does not go less than or equal to zero by having a lower limit of Tol*HF 
    # [NOTE: the value of dHF = ( Tol - 1.0 )*HF comes from: HF = HF + dHF = Tol*HF when dHF = ( Tol - 1.0 )*HF]
    #dX[0] = max( dX[0], ( tol - 1.0 )*info['HF']);  

    # To avoid an ill-conditioned situation, make sure HF does not get too close to zero, by forcing HF >= tols[0]
    #if info['HF'] + dX[0] <= tol*abs(info['VF']+dX[1]):
    #if info['HF'] + dX[0] <= tols[0]
    if X[0] + dX[0] <= tols[0]:
    #    dX[0] = tol*abs(info['VF']+dX[1]) - info['HF']   
    #    dX[0] = tols[0] - info['HF']   
        dX[0] = tols[0] - X[0]   


    # To avoid an ill-conditioned situation where the line is nearly all on the seabed but the solver gets stuck,
    #if np.abs(err[1] + ZF)/ZF < tol:
    #    breakpoint()
        #deltaHFVF = info['HF'] - info['VF']
        #dX[0] = dX[0] - 0.5*deltaHFVF
        #dX[1] = dX[1] + 0.5*deltaHFVF
    
    # prevent silly situation where a line with weight and positive ZF considers a negative VF
    if info["ProfileType"]==2:
        if X[1] + dX[1] <= tols[1]:                 # if vertical force is within tolerance of being zero/negative
            VFtarget = (L-info["LBot"])*W           # set next VF value to be the weight of portion of line that's suspended
            dX[1] = VFtarget - X[1]
    
    
    return dX                              # returns dX (step to make)

if __name__ == "__main__":
    import matplotlib.pyplot as plt
    
    '''
    (fAH, fAV, fBH, fBV, info) = catenary(37.96888656874307, 20.49078283711694, 100.0, 751000000.0, 
                                          -881.0549577007893, CB=-1245.2679469540894, 
                                          HF0=63442.20077641379, VF0=-27995.71383270186, Tol=1e-06, MaxIter=50, plots=2)
        
    
    #(fAH, fAV, fBH, fBV, info) = catenary(89.9, 59.2, 130.0, 751000000.0, 
    #                                      881.05, CB=-372.7, Tol=1e-06, MaxIter=50, plots=2)
     
    #(fAH, fAV, fBH, fBV, info) = catenary(400, 200, 500.0, 7510000000000.0, 200.0, CB=-372.7, Tol=1e-06, MaxIter=50, plots=3)
    #   
    '''
    
    '''
    #(fAH, fAV, fBH, fBV, info) = catenary(400, 200, 500.0, 7510000000000.0, 200.0, CB=5.0, Tol=1e-06, MaxIter=50, plots=3)
    (fAH, fAV, fBH, fBV, info) = catenary(400, 200, 500.0, 7510000000000.0, 200.0, CB=-20, Tol=1e-06, MaxIter=50, plots=3)
    
   
    print(f"Error is {info['catenary']['err'][0]:8.3f}, {info['catenary']['err'][1]:8.3f} m")
    
    print(" Fax={:8.2e}, Faz={:8.2e}, Fbx={:8.2e}, Fbz={:8.2e}".format(fAH, fAV, fBH, fBV))
    print(info['jacobian'])
    print(np.linalg.inv(info['jacobian']))
    '''
    
    #(fAH, fAV, fBH, fBV, info) = catenary(100, 20, 130, 1e12, 100.0, CB=-20, Tol=0.001, MaxIter=50, plots=3)
    #(fAH, fAV, fBH, fBV, info) = catenary(205, -3.9, 250, 1229760000.0, 2442, CB=-55, Tol=1e-06, MaxIter=50, plots=3)
    
    (fAH1, fAV1, fBH1, fBV1, info1) = catenary( 50, 20,  65, 1e12, 100.0, CB=  0, Tol=0.001, MaxIter=50, plots=4)
    (fAHU, fAVU, fBHU, fBVU, infoU) = catenary(100,  0, 130, 1e12, 100.0, CB=-20, Tol=0.001, MaxIter=50, plots=4)
    
    plt.plot(info1['X'], info1['Z'] )
    plt.plot(infoU['X'], infoU['Z'] )
    plt.axis('equal')
    plt.figure()
    plt.plot(info1['s'], info1['Te'] )
    plt.plot(infoU['s'], infoU['Te'] )
    
    plt.show()
