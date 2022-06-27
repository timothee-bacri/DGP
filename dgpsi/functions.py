from numba import jit, vectorize, float64
import numpy as np
from math import erf, exp, sqrt, pi
from numpy.random import randn
import itertools
from dill import dump, load

######Save and Load Emulators#######
def write(emu, pkl_file):
    """Save the constructed emulator to a pkl file.
    
    Args:
        emu (class): an emulator class. For GP, it is the 'gp' class after training. 
            For DGP, it is the 'emulator' class. For linked GP/DGP, it is the 'lgp' class.
        pkl_file (strings): specifies the path to and the name of the pkl file to which
            the emulator is saved.
    """
    dump(emu, open(pkl_file+".pkl","wb"))


def read(pkl_file):
    """Load the pkl file that stores the emulator.
    
    Args:
        pkl_file (strings): specifies the path to and the name of the pkl file where
            the emulator is stored.
    
    Returns:
        class: an emulator class. For GP, it is the 'gp' class. For DGP, it is the 'emulator' class. 
            For linked GP/DGP, it is the 'lgp' class.
    """
    emu = load(open(pkl_file+".pkl", "rb"))
    return emu

#######functions for optim#########
@jit(nopython=True,cache=True)
def pdist_matern_coef(X):
    n = X.shape[0]
    out_size = np.int((n * (n - 1)) / 2)
    dm = np.empty(out_size)
    k = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            dm[k] = matern_coef(X[i], X[j])
            k += 1
    return dm

@jit(nopython=True,cache=True)
def matern_coef(v,u):
    dist = 1
    for r in range(len(v)):
        disi = np.abs(v[r] - u[r])
        dist *= 1+np.sqrt(5)*disi+(5/3)*disi**2
    return dist

@jit(nopython=True,cache=True)
def fod_exp(X,K):
    n, D = X.shape
    dm = np.zeros((D,n,n))
    for d in range(D):
        for i in range(n - 1):
            for j in range(i + 1, n):
                temp = 2*(X[i,d]-X[j,d])**2*K[i,j]
                dm[d,i,j], dm[d,j,i] = temp, temp
    return dm

@jit(nopython=True,cache=True)
def pdist_matern_one(X):
    n = X.shape[0]
    dm = np.zeros((n,n))
    dm1 = np.zeros((1,n,n))
    for i in range(n - 1):
        for j in range(i + 1, n):
            temp1,temp2 = matern_one(X[i], X[j])
            dm[i,j], dm[j,i] = temp1, temp1 
            dm1[:,i,j], dm1[:,j,i] = temp2, temp2
    return dm, dm1

@jit(nopython=True,cache=True)
def pdist_matern_multi(X):
    n, D = X.shape
    dm = np.zeros((n,n))
    dm2 = np.zeros((D,n,n))
    for i in range(n - 1):
        for j in range(i + 1, n):
            temp1,temp2=matern_multi(X[i], X[j])
            dm[i,j], dm[j,i] = temp1, temp1 
            dm2[:,i,j], dm2[:,j,i] = temp2, temp2
    return dm, dm2

@jit(nopython=True,cache=True)
def matern_one(v,u):
    dist = 1
    dist1 = 0
    for d in range(len(v)):
        disi = np.abs(v[d] - u[d])
        coefi = 1+np.sqrt(5)*disi+(5/3)*disi**2
        dist *= coefi
        coefi1=(5/3)*(disi**2)*(1+np.sqrt(5)*disi)/(1+np.sqrt(5)*disi+5/3*disi**2)
        dist1 += coefi1
    return dist, dist1

@jit(nopython=True,cache=True)
def matern_multi(v,u):
    dist = 1
    dist1=np.zeros(len(v)) 
    for d in range(len(v)):
        disi = np.abs(v[d] - u[d])
        coefi = 1+np.sqrt(5)*disi+(5/3)*disi**2
        dist *= coefi
        coefi1=(5/3)*(disi**2)*(1+np.sqrt(5)*disi)/(1+np.sqrt(5)*disi+5/3*disi**2)
        dist1[d] = coefi1
    return dist, dist1

######functions for imputer########
@jit(nopython=True,cache=True)
def fmvn_mu(mu,cov):
    """Generate multivariate Gaussian random samples with means.
    """
    d=len(cov)
    sn=randn(d,1)
    L=np.linalg.cholesky(cov)
    samp=(L@sn).flatten()+mu
    return samp

@jit(nopython=True,cache=True)
def fmvn(cov):
    """Generate multivariate Gaussian random samples without means.
    """
    d=len(cov)
    sn=randn(d,1)
    L=np.linalg.cholesky(cov)
    samp=(L@sn).flatten()
    return samp

#@jit(nopython=True,cache=True)
#def fmvn_mu(mu,cov):
#    """Generate multivariate Gaussian random samples with means.
#    """
#    d=len(cov)
#    sn=randn(d,1)
#    U, s, _ = np.linalg.svd(cov)
#    samp=((U*np.sqrt(s))@sn).flatten() + mu
#    return samp

#@jit(nopython=True,cache=True)
#def fmvn(cov):
#    """Generate multivariate Gaussian random samples without means.
#    """
#    d=len(cov)
#    sn=randn(d,1)
#    U, s, _ = np.linalg.svd(cov)
#    samp=((U*np.sqrt(s))@sn).flatten()
#    return samp

@jit(nopython=True,cache=True)
def update_f(f,nu,theta):
    """Update ESS proposal samples.
    """
    fp=f*np.cos(theta) + nu*np.sin(theta)
    return fp
######Gauss-Hermite quadrature######
def ghdiag(fct,mu,var,y):
    x, w = np.polynomial.hermite.hermgauss(10)
    N = np.shape(mu)[1]
    const = np.pi**(-0.5*N)
    xn = np.array(list(itertools.product(*(x,)*N)))
    wn = np.prod(np.array(list(itertools.product(*(w,)*N))), 1)[:, None]
    fn = sqrt(2.0)*(np.sqrt(var[:,None])*xn) + mu[:,None]
    llik=fct(y[:,None],fn)
    return np.sum(np.exp(np.log((wn * const)[None,:]) + llik), axis=1)

######functions for predictions########
@jit(nopython=True,cache=True,fastmath=True)
def gp(x,z,w1,global_w1,Rinv,Rinv_y,scale,length,nugget,name):
    """Make GP predictions.
    """
    if z!=None:
        x=np.concatenate((x, z),1)
        w1=np.concatenate((w1, global_w1),1)
    r=k_one_vec(w1,x,length,name)
    Rinv_r=np.dot(Rinv,r)
    r_Rinv_r=np.sum(r*Rinv_r,axis=0)
    v=np.abs(scale*(1+nugget-r_Rinv_r))
    m=np.sum(r*Rinv_y,axis=0) 
    return m, v

@jit(nopython=True,cache=True,fastmath=True)
def link_gp(m,v,z,w1,global_w1,Rinv,Rinv_y,scale,length,nugget,name):
    """Make linked GP predictions.
    """
    M=len(m)
    m_new=np.empty((M,1))
    v_new=np.empty((M,1))
    if z!=None:
        Dw=np.shape(w1)[1]
        Dz=np.shape(z)[1]
        if len(length)==1:
            length=length*np.ones(Dw+Dz)
    else:
        Dw=np.shape(w1)[1]
        if len(length)==1:
            length=length*np.ones(Dw)
    for i in range(M):
        mi=m[i,:]
        vi=v[i,:]
        if z!=None:
            zi=np.expand_dims(z[i,:],axis=0)
            I,J=IJ(w1,mi,vi,length[:-Dz],name)
            Iz=k_one_vec(global_w1,zi,length[-Dz::],name)
            Iz_T=np.expand_dims(Iz.flatten(),axis=0)
            Jz=np.dot(Iz,Iz_T)
            I,J=I*Iz,J*Jz
        else:
            I,J=IJ(w1,mi,vi,length,name)
        tr_RinvJ=np.sum(Rinv*J.T)
        IRinv_y=np.sum(I*Rinv_y)
        m_new[i]=IRinv_y
        v_new[i]=np.abs(np.sum(np.sum(Rinv_y*J,axis=0)*Rinv_y.flatten())-IRinv_y**2+scale*(1+nugget-tr_RinvJ))
    return m_new.flatten(),v_new.flatten()

@jit(nopython=True,cache=True,fastmath=True)
def k_one_vec(X,z,length,name):
    """Compute cross-correlation matrix between the testing and training input data.
    """
    if name=='sexp':
        X_l=X/length
        z_l=z/length
        L_X=np.expand_dims(np.sum(X_l**2,axis=1),axis=1)
        L_z=np.expand_dims(np.sum(z_l**2,axis=1,),axis=1)
        dis2=L_X-2*np.dot(X_l,z_l.T)+L_z.T
        k=np.exp(-dis2)
    elif name=='matern2.5':
        n=np.shape(X)[0]
        d=np.shape(X)[1]
        m=len(z)
        X_l=np.expand_dims((X/length).T,axis=2)
        z_l=np.expand_dims((z/length).T,axis=2)
        k1=np.ones((n,m))
        k2=np.zeros((n,m))
        for i in range(d):
            dis=np.abs(X_l[i]-z_l[i].T)
            k1*=(1+sqrt(5)*dis+5/3*dis**2)
            k2+=dis
        k2=np.exp(-sqrt(5)*k2)
        k=k1*k2
    return k

@jit(nopython=True,cache=True,fastmath=True)
def IJ(X,z_m,z_v,length,name):
    """Compute I and J involved in linked GP predictions.
    """
    n=np.shape(X)[0]
    d=np.shape(X)[1]
    if name=='sexp':
        X_z=X-z_m
        I=np.ones((n,1))
        J=np.ones((n,n))
        for i in range(d):
            X_zi=np.ascontiguousarray(np.expand_dims(X_z[:,i],axis=1))
            X_zi_T=np.ascontiguousarray(np.expand_dims(X_z[:,i],axis=0))
            L_X_z=X_zi**2
            I*=1/np.sqrt(1+2*z_v[i]/length[i]**2)*np.exp(-L_X_z/(2*z_v[i]+length[i]**2))
            L_X_z_T=X_zi_T**2
            cross_L_X_z=np.dot(X_zi,X_zi_T)
            dis1=L_X_z+2*cross_L_X_z+L_X_z_T
            dis2=L_X_z-2*cross_L_X_z+L_X_z_T
            J*=1/np.sqrt(1+4*z_v[i]/length[i]**2)*np.exp(-dis1/(2*length[i]**2+8*z_v[i])-dis2/(2*length[i]**2))
    elif name=='matern2.5':
        zX=z_m-X
        muA=(zX-sqrt(5)*z_v/length).T.reshape((d,n,1))
        muB=(zX+sqrt(5)*z_v/length).T.reshape((d,n,1))
        zX=zX.T.reshape((d,n,1))
        X=X.T.reshape((d,n,1))
        I=np.ones((n,1))
        J=np.ones((n,n))
        for i in range(d):    
            if z_v[i]!=0:
                I*=np.exp((5*z_v[i]-2*sqrt(5)*length[i]*zX[i])/(2*length[i]**2))* \
                    ((1+sqrt(5)*muA[i]/length[i]+5*(muA[i]**2+z_v[i])/(3*length[i]**2))*pnorm(muA[i]/sqrt(z_v[i]))+ \
                    (sqrt(5)+(5*muA[i])/(3*length[i]))*sqrt(0.5*z_v[i]/pi)/length[i]*np.exp(-0.5*muA[i]**2/z_v[i]))+ \
                   np.exp((5*z_v[i]+2*sqrt(5)*length[i]*zX[i])/(2*length[i]**2))* \
                    ((1-sqrt(5)*muB[i]/length[i]+5*(muB[i]**2+z_v[i])/(3*length[i]**2))*pnorm(-muB[i]/sqrt(z_v[i]))+ \
                    (sqrt(5)-(5*muB[i])/(3*length[i]))*sqrt(0.5*z_v[i]/pi)/length[i]*np.exp(-0.5*muB[i]**2/z_v[i]))
                for k in range(n):
                    for l in range(k+1):
                        J_lk=Jd(X[i][l][0],X[i][k][0],z_m[i],z_v[i],length[i])
                        if l==k:
                            J[l,k]*=J_lk
                        else:
                            J[l,k]*=J_lk
                            J[k,l]*=J_lk
            else:
                Id=(1+sqrt(5)*np.abs(zX[i])/length[i]+5*zX[i]**2/(3*length[i]**2))*np.exp(-sqrt(5)*np.abs(zX[i])/length[i])
                I*=Id
                J*=np.dot(Id,Id.T)
    return I,J

@vectorize([float64(float64)],nopython=True,cache=True,fastmath=True)
def pnorm(x):
    """Compute standard normal CDF.
    """
    return 0.5*(1+erf(x/sqrt(2)))    

@jit(nopython=True,cache=True,fastmath=True)
def Jd(X1,X2,z_m,z_v,length):
    """Compute J components in different input dimensions for Matern2.5 kernel.
    """
    if X1<X2:
        x1=X1
        x2=X2
    else:
        x1=X2
        x2=X1
    E30=1+(25*x1**2*x2**2-3*sqrt(5)*(3*length**3+5*length*x1*x2)*(x1+x2)+15*length**2*(x1**2+x2**2+3*x1*x2))/(9*length**4)
    E31=(18*sqrt(5)*length**3+15*sqrt(5)*length*(x1**2+x2**2)-(75*length**2+50*x1*x2)*(x1+x2)+60*sqrt(5)*length*x1*x2)/(9*length**4)
    E32=5*(5*x1**2+5*x2**2+15*length**2-9*sqrt(5)*length*(x1+x2)+20*x1*x2)/(9*length**4)
    E33=10*(3*sqrt(5)*length-5*x1-5*x2)/(9*length**4)
    E34=25/(9*length**4)
    muC=z_m-2*sqrt(5)*z_v/length
    E3A31=E30+muC*E31+(muC**2+z_v)*E32+(muC**3+3*z_v*muC)*E33+(muC**4+6*z_v*muC**2+3*z_v**2)*E34
    E3A32=E31+(muC+x2)*E32+(muC**2+2*z_v+x2**2+muC*x2)*E33+(muC**3+x2**3+x2*muC**2+muC*x2**2+3*z_v*x2+5*z_v*muC)*E34
    P1=exp((10*z_v+sqrt(5)*length*(x1+x2-2*z_m))/length**2)*(0.5*E3A31*(1+erf((muC-x2)/sqrt(2*z_v)))+\
        E3A32*sqrt(0.5*z_v/pi)*exp(-0.5*(x2-muC)**2/z_v))
    
    E40=1+(25*x1**2*x2**2+3*sqrt(5)*(3*length**3-5*length*x1*x2)*(x2-x1)+15*length**2*(x1**2+x2**2-3*x1*x2))/(9*length**4)
    E41=5*(3*sqrt(5)*length*(x2**2-x1**2)+3*length**2*(x1+x2)-10*x1*x2*(x1+x2))/(9*length**4)
    E42=5*(5*x1**2+5*x2**2-3*length**2-3*sqrt(5)*length*(x2-x1)+20*x1*x2)/(9*length**4)
    E43=-50*(X1+X2)/(9*length**4)
    E44=25/(9*length**4)
    E4A41=E40+z_m*E41+(z_m**2+z_v)*E42+(z_m**3+3*z_v*z_m)*E43+(z_m**4+6*z_v*z_m**2+3*z_v**2)*E44
    E4A42=E41+(z_m+x1)*E42+(z_m**2+2*z_v+x1**2+z_m*x1)*E43+(z_m**3+x1**3+x1*z_m**2+z_m*x1**2+3*z_v*x1+5*z_v*z_m)*E44
    E4A43=E41+(z_m+x2)*E42+(z_m**2+2*z_v+x2**2+z_m*x2)*E43+(z_m**3+x2**3+x2*z_m**2+z_m*x2**2+3*z_v*x2+5*z_v*z_m)*E44
    P2=exp(-sqrt(5)*(x2-x1)/length)*(0.5*E4A41*(erf((x2-z_m)/sqrt(2*z_v))-erf((x1-z_m)/sqrt(2*z_v)))+\
        E4A42*sqrt(0.5*z_v/pi)*exp(-0.5*(x1-z_m)**2/z_v)-E4A43*sqrt(0.5*z_v/pi)*exp(-0.5*(x2-z_m)**2/z_v))

    E50=1+(25*x1**2*x2**2+3*sqrt(5)*(3*length**3+5*length*x1*x2)*(x1+x2)+15*length**2*(x1**2+x2**2+3*x1*x2))/(9*length**4)
    E51=(18*sqrt(5)*length**3+15*sqrt(5)*length*(x1**2+x2**2)+(75*length**2+50*x1*x2)*(x1+x2)+60*sqrt(5)*length*x1*x2)/(9*length**4)
    E52=5*(5*x1**2+5*x2**2+15*length**2+9*sqrt(5)*length*(x1+x2)+20*x1*x2)/(9*length**4)
    E53=10*(3*sqrt(5)*length+5*x1+5*x2)/(9*length**4)
    E54=25/(9*length**4)
    muD=z_m+2*sqrt(5)*z_v/length
    E5A51=E50-muD*E51+(muD**2+z_v)*E52-(muD**3+3*z_v*muD)*E53+(muD**4+6*z_v*muD**2+3*z_v**2)*E54
    E5A52=E51-(muD+x1)*E52+(muD**2+2*z_v+x1**2+muD*x1)*E53-(muD**3+x1**3+x1*muD**2+muD*x1**2+3*z_v*x1+5*z_v*muD)*E54
    P3=exp((10*z_v-sqrt(5)*length*(x1+x2-2*z_m))/length**2)*(0.5*E5A51*(1+erf((x1-muD)/sqrt(2*z_v)))+\
        E5A52*sqrt(0.5*z_v/pi)*exp(-0.5*(x1-muD)**2/z_v))

    jd=P1+P2+P3
    return jd