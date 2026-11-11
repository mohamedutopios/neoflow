package com.neosoft.neoflow.legacyia.analyse;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;

import java.io.UncheckedIOException;

/** Sérialisation JSON (Jackson, fourni par le SDK Anthropic) des faits et des rapports. */
public final class ExportJson {

    public static final ObjectMapper JSON = new ObjectMapper().enable(SerializationFeature.INDENT_OUTPUT);

    private ExportJson() {
    }

    public static String ecrire(Object objet) {
        try {
            return JSON.writeValueAsString(objet);
        } catch (JsonProcessingException e) {
            throw new UncheckedIOException(e);
        }
    }

    public static <T> T lire(String json, Class<T> type) {
        try {
            return JSON.readValue(json, type);
        } catch (JsonProcessingException e) {
            throw new UncheckedIOException(e);
        }
    }
}
