import numpy as np
from .imputation import imputer
import copy
from .functions import ghdiag

class emulator:
    """Class to make predictions from the trained DGP or DGP+likelihood model.

    Args:
        all_layer (list): a list that contains the trained DGP model produced by the method 'estimate'
            of the 'dgp' class. 
        N (int): the number of imputation to produce the predictions. Increase the value to account for
            more imputation uncertainties. Defaults to 50.
    """
    def __init__(self, all_layer,N=50):
        self.all_layer=all_layer
        self.n_layer=len(all_layer)
        self.imp=imputer(self.all_layer)
        (self.imp).sample(burnin=50)
        self.all_layer_set=[]
        for _ in range(N):
            (self.imp).sample()
            (self.all_layer_set).append(copy.deepcopy(self.all_layer))

    def predict(self,x,method='mean_var',full_layer=False,sample_size=50):
        """Implement predictions from the trained DGP model.

        Args:
            x (ndarray): a numpy 2d-array where each row is an input testing data point and 
                each column is an input dimension.
            method (str, optional): the prediction approach: mean-variance ('mean_var') or sampling 
                ('sampling') approach. Defaults to 'mean_var'.
            full_layer (bool, optional): whether to output the predictions of all layers. Defaults to False.
            sample_size (int, optional): the number of samples to draw for each given imputation. Defaults to 50.
            
        Returns:
            Union[tuple, list]: if the argument method='mean_var', a tuple is returned:
                    1. If full_layer=False, the tuple contains two numpy 2d-arrays, one for the predictive means 
                        and another for the predictive variances. Each array has its rows corresponding to testing 
                        positions and columns corresponding to DGP output dimensions (i.e., GP/likelihood nodes in the final layer);
                    2. If full_layer=True, the tuple contains two lists, one for the predictive means 
                        and another for the predictive variances. Each list contains L (i.e., the number of layers) 
                        numpy 2d-arrays. Each array has its rows corresponding to testing positions and columns 
                        corresponding to output dimensions (i.e., GP nodes from the associated layer and in case of the final layer, 
                        it may be the number of the likelihood nodes).
                if the argument method='sampling', a list is returned:
                    1. If full_layer=False, the list contains D (i.e., the number of GP/likelihood nodes in the final layer) numpy 
                        2d-arrays. Each array has its rows corresponding to testing positions and columns corresponding to
                        N imputations * sample_size;
                    2. If full_layer=True, the list contains L (i.e., the number of layers) sub-lists. Each sub-list 
                        represents the samples draw from the GPs/likelihoods in the corresponding layers, and contains 
                        D (i.e., the number of GP nodes in the corresponding layer or likelihood nodes in the final layer) 
                        numpy 2d-arrays. Each array gives samples of the output from one of D GPs/likelihoods at the 
                        testing positions, and has its rows corresponding to testing positions and columns corresponding to N imputations * sample_size.
        """
        M=len(x)
        if method=='mean_var':
            sample_size=1
        #start predictions
        mean_pred=[]
        variance_pred=[]
        likelihood_mean=[]
        likelihood_variance=[]
        for s in range(len(self.all_layer_set)):
            overall_global_test_input=x
            one_imputed_all_layer=self.all_layer_set[s]
            if full_layer==True:
                mean_pred_oneN=[]
                variance_pred_oneN=[]
            for l in range(self.n_layer):
                layer=one_imputed_all_layer[l]
                n_kerenl=len(layer)
                if l==self.n_layer-1:
                    likelihood_gp_mean=np.empty((M,n_kerenl))
                    likelihood_gp_var=np.empty((M,n_kerenl))
                else:
                    overall_test_output_mean=np.empty((M,n_kerenl))
                    overall_test_output_var=np.empty((M,n_kerenl))
                if l==0:
                    for k in range(n_kerenl):
                        kernel=layer[k]
                        m_k,v_k=kernel.gp_prediction(x=overall_global_test_input[:,kernel.input_dim],z=None)
                        overall_test_output_mean[:,k],overall_test_output_var[:,k]=m_k,v_k
                    overall_test_input_mean,overall_test_input_var=overall_test_output_mean,overall_test_output_var
                    if full_layer==True:
                        mean_pred_oneN.append(overall_test_input_mean)
                        variance_pred_oneN.append(overall_test_input_var)
                elif l==self.n_layer-1:
                    for k in range(n_kerenl):
                        kernel=layer[k]
                        m_k_in,v_k_in=overall_test_input_mean[:,kernel.input_dim],overall_test_input_var[:,kernel.input_dim]
                        if kernel.type=='gp':
                            if kernel.connect is not None:
                                z_k_in=overall_global_test_input[:,kernel.connect]
                            else:
                                z_k_in=None
                            m_k,v_k=kernel.linkgp_prediction(m=m_k_in,v=v_k_in,z=z_k_in)
                            likelihood_gp_mean[:,k],likelihood_gp_var[:,k]=m_k,v_k
                        elif kernel.type=='likelihood':
                            m_k,v_k=kernel.prediction(m=m_k_in,v=v_k_in)
                            likelihood_gp_mean[:,k],likelihood_gp_var[:,k]=m_k,v_k
                else:
                    for k in range(n_kerenl):
                        kernel=layer[k]
                        m_k_in,v_k_in=overall_test_input_mean[:,kernel.input_dim],overall_test_input_var[:,kernel.input_dim]
                        if kernel.connect is not None:
                            z_k_in=overall_global_test_input[:,kernel.connect]
                        else:
                            z_k_in=None
                        m_k,v_k=kernel.linkgp_prediction(m=m_k_in,v=v_k_in,z=z_k_in)
                        overall_test_output_mean[:,k],overall_test_output_var[:,k]=m_k,v_k
                    overall_test_input_mean,overall_test_input_var=overall_test_output_mean,overall_test_output_var
                    if full_layer==True:
                        mean_pred_oneN.append(overall_test_input_mean)
                        variance_pred_oneN.append(overall_test_input_var)
            for _ in range(sample_size):
                if full_layer==True:
                    mean_pred.append(mean_pred_oneN)
                    variance_pred.append(variance_pred_oneN)
                else:
                    mean_pred.append(overall_test_input_mean)
                    variance_pred.append(overall_test_input_var)
                likelihood_mean.append(likelihood_gp_mean)
                likelihood_variance.append(likelihood_gp_var)
        if method=='sampling':
            if full_layer==True:
                mu_layerwise=[list(mean_n) for mean_n in zip(*mean_pred)]
                var_layerwise=[list(var_n) for var_n in zip(*variance_pred)]
                samples=[]
                for l in range(self.n_layer):
                    samples_layerwise=[]
                    if l==self.n_layer-1:
                        for mu_likelihood, sigma2_likelihood, dgp_sample in zip(likelihood_mean, likelihood_variance, samples_layer_before_likelihood):
                            realisation=np.empty_like(mu_likelihood)
                            for count, kernel in enumerate(self.all_layer[-1]):
                                if kernel.type=='gp':
                                    realisation[:,count]=np.random.normal(mu_likelihood[:,count],np.sqrt(sigma2_likelihood[:,count]))
                                elif kernel.type=='likelihood':
                                    realisation[:,count]=kernel.sampling(dgp_sample[:,kernel.input_dim])
                            samples_layerwise.append(realisation)
                    else:
                        for mu, sigma2 in zip(mu_layerwise[l], var_layerwise[l]):
                            realisation=np.random.normal(mu,np.sqrt(sigma2))
                            samples_layerwise.append(realisation)
                        if l==self.n_layer-2:
                            samples_layer_before_likelihood=samples_layerwise
                    samples_layerwise=np.asarray(samples_layerwise).transpose(2,1,0)
                    samples.append(list(samples_layerwise))
            else:
                samples=[]
                for mu_dgp, sigma2_dgp, mu_likelihood, sigma2_likelihood  in zip(mean_pred, variance_pred, likelihood_mean, likelihood_variance):
                    realisation=np.empty_like(mu_likelihood)
                    for count, kernel in enumerate(self.all_layer[-1]):
                        if kernel.type=='gp':
                            realisation[:,count]=np.random.normal(mu_likelihood[:,count],np.sqrt(sigma2_likelihood[:,count]))
                        elif kernel.type=='likelihood':
                            dgp_sample=np.random.normal(mu_dgp,np.sqrt(sigma2_dgp))
                            realisation[:,count]=kernel.sampling(dgp_sample[:,kernel.input_dim])
                    samples.append(realisation)
                samples=list(np.asarray(samples).transpose(2,1,0))
            return samples
        elif method=='mean_var':
            if full_layer==True:
                mu_layerwise=[list(mean_n) for mean_n in zip(*mean_pred)]
                var_layerwise=[list(var_n) for var_n in zip(*variance_pred)]
                mu=[np.mean(mu_l,axis=0) for mu_l in mu_layerwise]
                mu2_mean=[np.mean(np.square(mu_l),axis=0) for mu_l in mu_layerwise]
                var_mean=[np.mean(var_l,axis=0) for var_l in var_layerwise]
                sigma2=[i+j-k**2 for i,j,k in zip(mu2_mean,var_mean,mu)]
                mu.append(np.mean(likelihood_mean,axis=0))
                sigma2.append(np.mean((np.square(likelihood_mean)+likelihood_variance),axis=0)-np.mean(likelihood_mean,axis=0)**2)
            else:
                mu=np.mean(likelihood_mean,axis=0)
                sigma2=np.mean((np.square(likelihood_mean)+likelihood_variance),axis=0)-mu**2
            return mu, sigma2

    def nllik(self,x,y):
        """Compute the negative predicted log-likelihood from the trained DGP model with likelihood layer.

        Args:
            x (ndarray): a numpy 2d-array where each row is an input testing data point and 
                each column is an input dimension.
            y (ndarray): a numpy 2d-array where each row is a scalar-valued testing output data point.

        Returns:
            tuple: a tuple of two 1d-arrays. The first one is the average negative predicted log-likelihood across
                   all testing data points. The second ones is the negative predicted log-likelihood for each testing data point.
        """
        if len(self.all_layer[-1])!=1:
            raise Exception('The method is only applicable to DGP with the final layer formed by only ONE node, which must be a likelihood node.')
        else:
            if self.all_layer[-1][0].type!='likelihood':
                raise Exception('The method is only applicable to DGP with the final layer formed by only ONE likelihood node, which must be a likelihood node.')
        M=len(x)
        #start predictions
        predicted_lik=[]
        for s in range(len(self.all_layer_set)):
            overall_global_test_input=x
            one_imputed_all_layer=self.all_layer_set[s]
            for l in range(self.n_layer-1):
                layer=one_imputed_all_layer[l]
                n_kerenl=len(layer)
                overall_test_output_mean=np.empty((M,n_kerenl))
                overall_test_output_var=np.empty((M,n_kerenl))
                if l==0:
                    for k in range(n_kerenl):
                        kernel=layer[k]
                        m_k,v_k=kernel.gp_prediction(x=overall_global_test_input[:,kernel.input_dim],z=None)
                        overall_test_output_mean[:,k],overall_test_output_var[:,k]=m_k,v_k
                    overall_test_input_mean,overall_test_input_var=overall_test_output_mean,overall_test_output_var
                else:
                    for k in range(n_kerenl):
                        kernel=layer[k]
                        m_k_in,v_k_in=overall_test_input_mean[:,kernel.input_dim],overall_test_input_var[:,kernel.input_dim]
                        if kernel.connect is not None:
                            z_k_in=overall_global_test_input[:,kernel.connect]
                        else:
                            z_k_in=None
                        m_k,v_k=kernel.linkgp_prediction(m=m_k_in,v=v_k_in,z=z_k_in)
                        overall_test_output_mean[:,k],overall_test_output_var[:,k]=m_k,v_k
                    overall_test_input_mean,overall_test_input_var=overall_test_output_mean,overall_test_output_var
            predicted_lik.append(ghdiag(one_imputed_all_layer[-1][0].pllik,overall_test_input_mean,overall_test_input_var,y))
        nllik=-np.log(np.mean(predicted_lik,axis=0)).flatten()
        average_nllik=np.mean(nllik)
        return average_nllik, nllik

        
      