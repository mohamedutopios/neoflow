# Image du backend NeoFlow (profil dev, PostgreSQL et Jaeger fournis par docker compose).
FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY .mvn/ .mvn/
COPY mvnw pom.xml ./
RUN chmod +x mvnw && ./mvnw -B -q dependency:go-offline
COPY src/ src/
RUN ./mvnw -B -q -DskipTests package && cp target/neoflow-backend-*.jar /src/app.jar

FROM eclipse-temurin:21-jre
WORKDIR /app
RUN groupadd --system neoflow && useradd --system --gid neoflow --uid 10001 neoflow
COPY --from=build /src/app.jar /app/app.jar
USER neoflow
EXPOSE 8080
ENV SPRING_PROFILES_ACTIVE=dev
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
