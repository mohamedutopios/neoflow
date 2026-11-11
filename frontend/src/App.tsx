import { Navigate, Route, Routes } from 'react-router-dom';

import { Layout } from './components/Layout';
import { RouteProtegee } from './components/RouteProtegee';
import { DemandeDetail } from './pages/DemandeDetail';
import { DemandeFormulaire } from './pages/DemandeFormulaire';
import { DemandesListe } from './pages/DemandesListe';
import { LoginPage } from './pages/LoginPage';

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/connexion" element={<LoginPage />} />
        <Route
          path="/demandes"
          element={
            <RouteProtegee>
              <DemandesListe />
            </RouteProtegee>
          }
        />
        <Route
          path="/demandes/nouvelle"
          element={
            <RouteProtegee>
              <DemandeFormulaire />
            </RouteProtegee>
          }
        />
        <Route
          path="/demandes/:id"
          element={
            <RouteProtegee>
              <DemandeDetail />
            </RouteProtegee>
          }
        />
        <Route
          path="/demandes/:id/modifier"
          element={
            <RouteProtegee>
              <DemandeFormulaire />
            </RouteProtegee>
          }
        />
        <Route path="*" element={<Navigate to="/demandes" replace />} />
      </Route>
    </Routes>
  );
}
